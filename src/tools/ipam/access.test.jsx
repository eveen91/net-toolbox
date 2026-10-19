import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { hasToolAccess, visibleTools } from "../registry.js";
import AddressPopover from "./AddressPopover.jsx";
import TagSelector from "./TagSelector.jsx";
import IpamToolbar from "./IpamToolbar.jsx";

vi.mock('../../auth/AuthContext.jsx',async original=>({...await original(),useAuth:()=>({user:{permissions:['ipam.read']},loginRequired:true})}));

const address = { id: 1, address: "10.0.0.1", status: "used", allocationType: "static", updatedAt: "2026-01-01" };
function enabledButton(html, text) {
  return [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].some(([, attributes, content]) => content.trim() === text && !attributes.includes("disabled"));
}

describe("IPAM access through the application shell and nested controls", () => {
  it("exposes IPAM to a granular reader without granting other tools", () => {
    expect(hasToolAccess(["ipam.read"], "ipam")).toBe(true);
    expect(visibleTools({ permissions: ["ipam.read"] }, true).map((tool) => tool.id)).toEqual(["ipam"]);
    expect(hasToolAccess(["ipam.scan"], "ipam")).toBe(false);
    expect(hasToolAccess(["ipam.read"], "troubleshoot")).toBe(false);
  });
  it("keeps read-only address details visible while disabling write and scan actions", () => {
    const html = renderToStaticMarkup(<AddressPopover ip={address.address} address={address} subnetId={1} coords={{ x: 0, y: 0 }} canWrite={false} canScan={false} canAdmin={false} />);
    expect(html).toContain("10.0.0.1");
    for (const action of ["Edit", "Delete", "Rescan", "+ New tag"]) expect(enabledButton(html, action)).toBe(false);
  });
  it("allows scan independently from write", () => {
    const html = renderToStaticMarkup(<AddressPopover ip={address.address} address={address} subnetId={1} coords={{ x: 0, y: 0 }} canWrite={false} canScan={true} canAdmin={false} />);
    expect(enabledButton(html, "Rescan")).toBe(true);
    expect(enabledButton(html, "Edit")).toBe(false);
  });
  it("permits assigning existing tags without exposing admin-only tag creation", () => {
    const html = renderToStaticMarkup(<TagSelector value={[]} allTags={[]} canCreate={false} onChange={() => {}} />);
    expect(html).not.toContain("+ New tag");
    expect(enabledButton(html, "▸ Tags")).toBe(true);
  });
  it("keeps archive browsing and dashboard accessible to readers", () => {
    const html = renderToStaticMarkup(<IpamToolbar subnets={[]} tags={[]} selectedTagIds={[]} permissions={{ read: true, write: false, scan: false, admin: false }} />);
    expect(enabledButton(html, "Archive")).toBe(true);
    expect(enabledButton(html, "Overview")).toBe(true);
    expect(enabledButton(html, "Import")).toBe(false);
    expect(enabledButton(html, "Allocator")).toBe(false);
  });
});
