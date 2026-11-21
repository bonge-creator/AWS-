"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { AdminStats, Role, User } from "@/lib/types";
import { PageHeader } from "@/components/ui";

const ROLES: Role[] = ["admin", "analyst", "viewer"];

export default function AdminPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    email: "",
    display_name: "",
    password: "",
    role: "viewer" as Role,
  });

  async function load() {
    try {
      const [u, s] = await Promise.all([api.adminUsers(), api.adminStats()]);
      setUsers(u.items);
      setStats(s);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load admin data.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.adminCreateUser(form);
      setForm({ email: "", display_name: "", password: "", role: "viewer" });
      setCreating(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create user.");
    }
  }

  async function changeRole(user: User, role: Role) {
    try {
      await api.adminUpdateUser(user.id, { role });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Update failed.");
    }
  }

  async function toggleActive(user: User) {
    try {
      await api.adminUpdateUser(user.id, { is_active: !user.is_active });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Update failed.");
    }
  }

  return (
    <div className="grid-field min-h-screen">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <PageHeader
          eyebrow="Administration"
          title="Users & access"
          description="Roles decide which documents a person may reach before retrieval runs. A role change takes effect on the very next query."
          actions={
            <button className="btn btn-primary" onClick={() => setCreating((c) => !c)}>
              {creating ? "Cancel" : "Add user"}
            </button>
          }
        />

        {error && (
          <div className="mt-4 rounded-lg border border-[#B3261E]/25 bg-[#B3261E]/6 px-3.5 py-2.5 text-[12px] text-[#B3261E]">
            {error}
          </div>
        )}

        {stats && (
          <div className="mt-6 grid gap-3 sm:grid-cols-5">
            {[
              ["Users", stats.users],
              ["Documents", stats.documents],
              ["Ready", stats.ready_documents],
              ["Conversations", stats.conversations],
              ["Citations", stats.citations],
            ].map(([k, v]) => (
              <div key={k as string} className="panel p-4 shadow-panel">
                <p className="label">{k}</p>
                <p className="mt-1 font-mono text-[20px] font-semibold">{v}</p>
              </div>
            ))}
          </div>
        )}

        {creating && (
          <form onSubmit={create} className="panel mt-5 grid gap-3 p-5 shadow-panel sm:grid-cols-2">
            <div>
              <label className="label mb-1.5 block">Email</label>
              <input
                className="input"
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div>
              <label className="label mb-1.5 block">Display name</label>
              <input
                className="input"
                required
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              />
            </div>
            <div>
              <label className="label mb-1.5 block">Password</label>
              <input
                className="input"
                type="password"
                required
                minLength={8}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </div>
            <div>
              <label className="label mb-1.5 block">Role</label>
              <select
                className="input"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <button className="btn btn-primary" type="submit">
                Create user
              </button>
            </div>
          </form>
        )}

        <div className="mt-6 overflow-hidden rounded-xl border border-charcoal/10 bg-white">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-charcoal/10 bg-charcoal/[0.02]">
                <th className="label px-4 py-2.5 font-semibold">User</th>
                <th className="label px-4 py-2.5 font-semibold">Role</th>
                <th className="label px-4 py-2.5 font-semibold">Status</th>
                <th className="label px-4 py-2.5 font-semibold">Created</th>
                <th className="label px-4 py-2.5 font-semibold" />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-charcoal/5 last:border-0">
                  <td className="px-4 py-3">
                    <p className="text-[13px] font-medium">{u.display_name}</p>
                    <p className="text-[11px] text-steel">{u.email}</p>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      className="input max-w-[130px] py-1.5 text-[12px]"
                      value={u.role}
                      onChange={(e) => changeRole(u, e.target.value as Role)}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`chip ${
                        u.is_active
                          ? "bg-[#2F6F4F]/12 text-[#2F6F4F]"
                          : "bg-charcoal/8 text-steel"
                      }`}
                    >
                      {u.is_active ? "active" : "disabled"}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-charcoal/55">
                    {u.created_at?.slice(0, 10)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      className="text-[12px] font-medium text-charcoal/55 hover:text-copper"
                      onClick={() => toggleActive(u)}
                    >
                      {u.is_active ? "Disable" : "Enable"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
