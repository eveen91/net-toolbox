import { apiFetch } from "../../apiFetch.js";

export async function fetchPlans() {
  const res = await apiFetch("/api/validation/plans");
  if (!res.ok) throw new Error("Failed to fetch plans");
  return res.json();
}

export async function createPlan(data) {
  const res = await apiFetch("/api/validation/plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create plan");
  return res.json();
}

export async function getPlan(id) {
  const res = await apiFetch(`/api/validation/plans/${id}`);
  if (!res.ok) throw new Error("Failed to fetch plan details");
  return res.json();
}

export async function deletePlan(id) {
  const res = await apiFetch(`/api/validation/plans/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete plan");
  return res.json();
}

export async function saveBaseline(data) {
  const res = await apiFetch("/api/validation/baselines", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to save baseline");
  return res.json();
}
