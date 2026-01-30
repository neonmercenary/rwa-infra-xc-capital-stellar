
# XC Capital — Institutional Cashflow Settlement Infrastructure on Stellar/Soroban

## Overview

XC Capital provides institutional-grade infrastructure for issuing, accounting, and settling Business Purpose Lending (BPL) cashflows on Stellar via Soroban smart contracts.

The system ensures that real-world credit cashflows are:

- Deterministically reflected on-chain  
- Issuer-controlled yet transparent to investors  
- Compliant with regulated asset standards  

XC Capital is **not** a marketplace, fund wrapper, or speculative token protocol. It is financial infrastructure: plumbing that enables private credit instruments to exist credibly on-chain with verifiable yield computation.

---

## Mission

Enable settlement of Business Purpose Lending instruments (10–14% yield notes) with:

- Deterministic yield accounting  
- Transparent investor reporting  
- Secure issuer execution  
- Global settlement access  

---

## Migration Context

### Legacy System

The architecture was initially prototyped on Avalanche using Vyper contracts and Django services. Core logic validated:

- Deterministic on-chain yield  
- Tokenized tranche representation  
- Issuer-controlled distributions  
- Read-only investor dashboards  

### Stellar/Soroban Transition

The migration aligns the system with Stellar’s production capabilities:

- **SEP-8 Regulated Assets:** protocol-level compliance and transaction gating  
- **SEP-10 Authentication:** secure Web login for admin/issuer actions  
- **SEP-24 Anchors:** global fiat/USDC deposits and payouts  
- **I256 math:** high-precision yield calculations for institutional-grade accounting  

---

## Key Innovation

Dual-portal architecture:

1. **Admin Plane (SPV / Operator)**  
   - Issue BPL instruments  
   - Trigger investor payouts  
   - Perform compliance checks  

2. **Investor Plane (Read-only)**  
   - View balances  
   - Track accrued yield  
   - Verify payouts  

All actions maintain a strict separation of duties. Investor private keys are never exposed.

---

## Smart Contract Design (Soroban)

- Multi-instrument accounting  
- Deterministic yield accrual  
- Transfer-restricted lifecycle  
- Issuer-controlled settlement  

**Precision Model:**  
- i128 for storage  
- I256 for intermediate math  

Contracts focus on **state correctness and yield computation**, not custody or legal compliance.

---

## Compliance Framework

- SEP-8 Regulated Assets: protocol-level transaction approval  
- Ensures jurisdictional controls and auditability  
- Replaces prior manual on-chain checks  

---

## Authentication Model

- SEP-10 Web Authentication for admin portal  
- Secure identity verification and transaction authorization  

---

## Settlement Workflow

- Investors deposit via SEP-24 anchors  
- USDC-based yield distributions executed  
- Recurring micro-distributions processed efficiently  
- Investors globally can participate without crypto custody complexity  

---

## Air-Gapped Administrative Security

- Administrative transactions drafted in SPV portal  
- Signed in an isolated, offline environment  
- Broadcasted securely to Stellar network  

Master keys **never touch the internet**.

---

## Cashflow Lifecycle

1. SPV originates a real-world BPL loan  
2. Corresponding instrument created on Soroban  
3. Investor positions issued  
4. Borrower payments occur off-chain  
5. SPV mirrors payments on-chain  
6. Yield accrues deterministically  
7. Distributions executed  
8. Investors verify outcomes on-chain  

---

## Directory Structure

```

xc-capital/

├── README.md
├── contracts/
│   ├── vyper/                # Legacy specification reference
│   └── soroban/              # Active Rust servicing engine
│       ├── src/
│       ├── tests/
│       └── Cargo.toml
├── spv_admin/                # Django backend (Anchor/Auth server)
├── investor_portal/          # Read-only investor interface
└── diagrams/                 # Architecture & flow diagrams

```

---

## Deployment & Testing

- **Networks:** Soroban Testnet / Futurenet  
- **Framework:** soroban-sdk test utilities  
- High-precision interest simulations  
- Settlement flow validation  

---

## Intended Use Cases

- Business Purpose Lending (BPL)  
- Private credit markets  
- Structured debt instruments  
- Asset-backed notes  
- Institutional RWA pilots  

---

## Design Principles

- Cashflow integrity over token hype  
- Issuer control over automation  
- Deterministic accounting over governance  
- Compliance alignment over abstraction  
- Security over convenience  

---

## Status

- Core accounting logic validated  
- Soroban migration in progress  
- Compliance integration underway  
- Testnet deployment planned  

---

## Legacy Reference

The architecture and logic were initially prototyped on Avalanche (see [legacy repo](https://github.com/neonmercenary/rwa-structured-finance-infra/)).  
All core accounting and settlement mechanisms have been preserved in this Stellar/Soroban migration.

---

## Disclaimer

This repository provides infrastructure tooling and does not constitute an investment offering. Regulatory compliance is the responsibility of the issuer.

