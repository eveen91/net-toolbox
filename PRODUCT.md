# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Mixed operations teams spanning network engineering, systems administration, and security. They use the product to calculate, inspect, validate, troubleshoot, and manage network infrastructure from one workspace.

## Product Purpose

`net::toolbox` consolidates routine network operations into a single application. It combines browser-based calculators with backend-powered workflows for connectivity testing, routing data, IP address management, multi-vendor troubleshooting, and post-change validation. Success means operators can move from question or incident to a verified result without switching among disconnected utilities.

## Positioning

A unified operations workspace that brings IPAM, troubleshooting, validation, routing, and network calculations together while remaining self-hosted and suitable for mixed infrastructure teams.

## Operating Context

Teams use `net::toolbox` during day-to-day network administration, incident troubleshooting, address planning, infrastructure changes, and post-change verification. Workflows may involve Cisco IOS, Aruba CX, Check Point Gaia, Linux over SSH, Windows over WinRM, local authentication, or Active Directory.

## Capabilities and Constraints

- Preserve self-hosted operation, including local development and Docker deployment.
- Preserve multi-vendor networking workflows across Cisco, Aruba, Check Point, Linux, and Windows systems.
- Preserve local and Active Directory authentication, sessions, custom roles, and feature-level permissions.
- Keep credentials scoped to their documented workflows and do not imply that transient credentials are stored.
- Use only repository-backed product capabilities and evidence; do not fabricate claims, integrations, benchmarks, customers, or outcomes.
- The existing implementation uses React 18 with Vite for the frontend and FastAPI with SQLite for backend services and persistence.

## Brand Commitments

The product name is `net::toolbox`. Product language should be direct, operational, and technically precise.

## Evidence on Hand

- Product capabilities and architecture: `README.md`.
- Working React application and tool registry: `src/`.
- FastAPI endpoints, authentication, persistence, automation, and tests: `server/`.
- Docker deployment materials: `docker/`.
- No customer testimonials, usage benchmarks, case studies, or external validation are currently provided and must not be invented.

## Product Principles

- Unify related operational tasks without obscuring their technical detail.
- Make system state, validation results, and failures explicit and actionable.
- Respect mixed-team access boundaries through authentication and role-based permissions.
- Support heterogeneous infrastructure without pretending vendors and operating systems behave identically.
- Keep deployment and operational data under the organization’s control.
