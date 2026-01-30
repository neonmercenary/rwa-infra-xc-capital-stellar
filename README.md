# XC Capital — Institutional Cashflow Settlement Infrastructure on Stellar/Soroban

## Overview

XC Capital is a planned institutional-grade infrastructure for issuing, accounting, and settling Business Purpose Lending (BPL) cashflows on Stellar. By leveraging upcoming **Soroban smart contracts**, the project aims to bridge real-world credit with blockchain efficiency.

The system is designed to ensure that real-world credit cashflows will be:

* Deterministically reflected on-chain
* Issuer-controlled yet transparent to investors
* Compliant with regulated asset standards

XC Capital is **not** a marketplace, fund wrapper, or speculative token protocol. It is financial infrastructure: the "plumbing" intended to enable private credit instruments to exist credibly on-chain with verifiable yield computation.

---

## Mission

Build a framework to enable settlement of Business Purpose Lending instruments (10–14% yield notes) with:

* Deterministic yield accounting
* Transparent investor reporting
* Secure issuer execution
* Global settlement access

---

## Migration Context

### Legacy System

The architecture was initially prototyped on Avalanche using Vyper contracts and Django services. Core logic was validated for:

* Deterministic on-chain yield
* Tokenized tranche representation
* Issuer-controlled distributions
* Read-only investor dashboards

### Planned Stellar/Soroban Transition

The upcoming migration will align the system with Stellar’s production capabilities:

* **SEP-8 Regulated Assets:** Planned protocol-level compliance and transaction gating.
* **SEP-10 Authentication:** Proposed secure Web login for admin/issuer actions.
* **SEP-24 Anchors:** Future integration for global fiat/USDC deposits and payouts.
* **I256 math:** Implementation of high-precision yield calculations for institutional-grade accounting.

---

## Key Innovation

The proposed dual-portal architecture:

1. **Admin Plane (SPV / Operator)** - Tools to issue BPL instruments
* Mechanisms to trigger investor payouts
* Automated compliance checks


2. **Investor Plane (Read-only)** - Dashboards to view balances
* Interface to track accrued yield
* Verifiable payout history



All planned actions maintain a strict separation of duties. Investor private keys are never to be exposed.

---

## Smart Contract Design (Proposed Soroban Implementation)

* Multi-instrument accounting
* Deterministic yield accrual
* Transfer-restricted lifecycle
* Issuer-controlled settlement

**Precision Model:** - `i128` for storage

* `I256` for intermediate math

Contracts will focus on **state correctness and yield computation**, rather than custody or legal compliance.

---

## Compliance Framework

* **SEP-8 Regulated Assets:** Intended for protocol-level transaction approval.
* Designed to ensure jurisdictional controls and auditability.
* Objective: Replace prior manual on-chain checks with native Stellar standards.

---

## Authentication Model

* **SEP-10 Web Authentication:** Planned for the admin portal.
* Aimed at providing secure identity verification and transaction authorization.

---

## Settlement Workflow (Concept)

* Investors will deposit via SEP-24 anchors.
* USDC-based yield distributions to be executed on-chain.
* Recurring micro-distributions to be processed efficiently.
* Goal: Enable global participation without crypto custody complexity.

---

## Air-Gapped Administrative Security

* Administrative transactions to be drafted in the SPV portal.
* Signing to be handled in an isolated, offline environment.
* Secure broadcasting to the Stellar network.

Master keys are designed to **never touch the internet**.

---

## Proposed Cashflow Lifecycle

1. SPV originates a real-world BPL loan.
2. Corresponding instrument to be created on Soroban.
3. Investor positions to be issued.
4. Borrower payments occur off-chain.
5. SPV will mirror payments on-chain.
6. Yield will accrue deterministically.
7. Distributions to be executed.
8. Investors will verify outcomes on-chain.

---

## Directory Structure (Planned)

```text
xc-capital/
├── README.md
├── contracts/
│   ├── vyper/             # Legacy specification reference
│   └── soroban/           # Future Rust servicing engine (To be built)
│       ├── src/
│       ├── tests/
│       └── Cargo.toml
├── spv_admin/             # Planned Django backend (Anchor/Auth server)
├── investor_portal/       # Planned read-only investor interface
└── diagrams/              # Architecture & flow diagrams

```

---

## Deployment & Testing Roadmap

* **Target Networks:** Soroban Testnet / Futurenet
* **Framework:** `soroban-sdk` test utilities
* Planned high-precision interest simulations.
* Planned settlement flow validation.

---

## Intended Use Cases

* Business Purpose Lending (BPL)
* Private credit markets
* Structured debt instruments
* Asset-backed notes
* Institutional RWA pilots

---

## Design Principles

* Cashflow integrity over token hype
* Issuer control over automation
* Deterministic accounting over governance
* Compliance alignment over abstraction
* Security over convenience

---

## Status

* **Core accounting logic:** Validated (Legacy)
* **Soroban migration:** In planning / Pre-development
* **Compliance integration:** Under research
* **Testnet deployment:** Scheduled

---

## Legacy Reference

The architecture and logic were initially prototyped on Avalanche (see [legacy repo](https://github.com/neonmercenary/rwa-structured-finance-infra/)).

All core accounting and settlement mechanisms are intended to be preserved in this upcoming Stellar/Soroban migration.

---

## Disclaimer

This repository is intended to provide infrastructure tooling and does not constitute an investment offering. Regulatory compliance is the responsibility of the issuer.

---
