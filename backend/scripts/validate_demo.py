"""End-to-end validation of the five live demo tests.

Runs the real ASGI application against the real database and the real Bedrock
model, as each of the three seeded users, and asserts the five behaviours the
brief calls for. Nothing is stubbed: the answers come from the same code path
the browser uses.

    ./.venv/Scripts/python -m scripts.validate_demo
"""

import asyncio
import json
import sys

import httpx

from app.main import app

BASE = "http://testserver"
PASSWORD = "Archive!2026"

PASSED = "\033[32mPASS\033[0m"
FAILED = "\033[31mFAIL\033[0m"


class Result:
    def __init__(self):
        self.rows = []

    def check(self, name, condition, detail=""):
        self.rows.append((name, bool(condition), detail))
        mark = PASSED if condition else FAILED
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
        return bool(condition)

    @property
    def failed(self):
        return [r for r in self.rows if not r[1]]


async def login(client, email):
    res = await client.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    res.raise_for_status()
    body = res.json()
    return body["access_token"], body["refresh_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def ask(client, token, question):
    res = await client.post(
        f"{BASE}/api/v1/chat/ask", json={"question": question}, headers=auth(token)
    )
    res.raise_for_status()
    return res.json()


async def list_docs(client, token):
    res = await client.get(f"{BASE}/api/v1/documents", headers=auth(token))
    res.raise_for_status()
    return res.json()["items"]


async def main():
    transport = httpx.ASGITransport(app=app)
    r = Result()

    from app.db.session import keepalive

    async with keepalive(), httpx.AsyncClient(
        transport=transport, base_url=BASE, timeout=300.0
    ) as client:
        print("\n== Authentication ==")
        tokens = {}
        for role in ("admin", "analyst", "viewer"):
            try:
                tokens[role] = await login(client, f"{role}@archivedemo.example.com")
                r.check(f"{role} can log in", True)
            except Exception as exc:  # noqa: BLE001
                r.check(f"{role} can log in", False, str(exc))
        if r.failed:
            await finish(r)
            return

        admin, analyst, viewer = (tokens[k][0] for k in ("admin", "analyst", "viewer"))

        # ------------------------------------------------------------------
        print("\n== TEST 1 — lease agreements expiring next year ==")
        answer = await ask(
            client, admin, "Which lease agreements are expiring next year?"
        )
        r.check("answer is found, not abstained", answer["found"], answer["answer"][:120])
        r.check("intent is the deterministic metadata path",
                answer["intent"] != "semantic", f"intent={answer['intent']}")
        cited = {c["filename"] for c in answer["citations"]}
        # 2027 leases: harbour-street, meridian-park. 2026 lease excluded.
        r.check("harbour-street lease (2027) is cited",
                "harbour-street-lease.pdf" in cited, str(sorted(cited)))
        r.check("meridian-park lease (2027) is cited",
                "meridian-park-lease.pdf" in cited, str(sorted(cited)))
        r.check("northgate lease (2026) is excluded",
                "northgate-warehouse-lease.pdf" not in cited, str(sorted(cited)))
        r.check("exactly two leases cited", len(cited) == 2, str(sorted(cited)))

        # ------------------------------------------------------------------
        print("\n== TEST 2 — summary of a selected contract ==")
        docs = await list_docs(client, admin)
        contract = next(
            (d for d in docs if d["filename"] == "kestrel-facilities-contract.pdf"), None
        )
        r.check("contract is present in the archive", contract is not None)
        if contract:
            res = await client.post(
                f"{BASE}/api/v1/summaries/{contract['id']}", headers=auth(admin)
            )
            r.check("summary generated", res.status_code == 200, f"HTTP {res.status_code}")
            if res.status_code == 200:
                summary = res.json()
                r.check("summary is non-trivial", len(summary["summary"]) > 200,
                        f"{len(summary['summary'])} chars")
                r.check("summary names a real model",
                        summary["model"] != "", summary["model"])
                print(f"       model: {summary['model']}")

        # ------------------------------------------------------------------
        print("\n== TEST 3 — citation opens the original document ==")
        answer = await ask(
            client, admin, "What is the total contract value and the rent schedule?"
        )
        cites = answer["citations"]
        r.check("answer carries citations", len(cites) > 0, f"{len(cites)} citations")
        if cites:
            c = cites[0]
            r.check("citation has a document, page range and quote",
                    bool(c["document_id"]) and c["page_start"] >= 1 and bool(c["quote"]),
                    f"{c['filename']} p.{c['page_start']}-{c['page_end']}")
            res = await client.get(
                f"{BASE}/api/v1/documents/{c['document_id']}/preview",
                headers=auth(admin),
            )
            r.check("preview for the cited document opens", res.status_code == 200,
                    f"HTTP {res.status_code}")
            if res.status_code == 200:
                body = res.json()
                pages = body.get("pages", [])
                r.check("preview contains the cited page",
                        any(p["page_start"] <= c["page_start"] <= p["page_end"]
                            for p in pages),
                        f"{len(pages)} pages")

        # ------------------------------------------------------------------
        print("\n== TEST 4 — two users, same question, different answers ==")
        q = "What are the security and data protection obligations?"
        a_analyst = await ask(client, analyst, q)
        a_viewer = await ask(client, viewer, q)
        a_admin = await ask(client, admin, q)

        def names(ans):
            return {c["filename"] for c in ans["citations"]}

        r.check("admin sees the NDA (admin-only document)",
                any("nda" in n for n in names(a_admin)),
                str(sorted(names(a_admin))))
        r.check("analyst does NOT see the NDA",
                not any("nda" in n for n in names(a_analyst)),
                str(sorted(names(a_analyst))))
        r.check("viewer does NOT see the NDA",
                not any("nda" in n for n in names(a_viewer)),
                str(sorted(names(a_viewer))))
        r.check("analyst and viewer citations differ",
                names(a_analyst) != names(a_viewer),
                f"analyst={sorted(names(a_analyst))} viewer={sorted(names(a_viewer))}")
        r.check("viewer cannot reach the analyst-only warehouse lease",
                not any("northgate" in n for n in names(a_viewer)),
                str(sorted(names(a_viewer))))

        # Direct API check: the viewer is refused the NDA outright.
        nda = next((d for d in docs if "nda" in d["filename"]), None)
        if nda:
            res = await client.get(
                f"{BASE}/api/v1/documents/{nda['id']}", headers=auth(viewer)
            )
            r.check("viewer is denied direct access to the NDA",
                    res.status_code == 403, f"HTTP {res.status_code}")

        # ------------------------------------------------------------------
        print("\n== TEST 5 — honest 'I don't know' ==")
        answer = await ask(
            client, admin,
            "What is the win probability of the Q3 2027 satellite launch programme?",
        )
        r.check("answer is flagged as not found", not answer["found"],
                answer["answer"][:120])
        r.check("no citations are offered", len(answer["citations"]) == 0,
                str(len(answer["citations"])))
        lowered = answer["answer"].lower()
        r.check("answer says the archive does not contain it",
                ("not contain" in lowered or "not in the archive" in lowered
                 or "do not have" in lowered or "no " in lowered),
                answer["answer"][:160])

        # A question the archive *does* contain must not abstain.
        answer = await ask(client, admin, "Which lease agreements are expiring next year?")
        r.check("a known question is answered", answer["found"])

    await finish(r)


async def finish(r):
    print("\n" + "=" * 62)
    total = len(r.rows)
    passed = total - len(r.failed)
    if r.failed:
        print(f"{FAILED} {passed}/{total} checks passed. Failing checks:")
        for name, _, detail in r.failed:
            print(f"  · {name}" + (f" — {detail}" if detail else ""))
        sys.exit(1)
    print(f"{PASSED} all {total} checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
