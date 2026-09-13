# Provenance and development conditions

**Project:** Northstar
**Author:** Marcos Mucapera
**Statement first recorded:** 2026-09-13

---

## Purpose of this document

This file records the conditions under which this repository is developed. It is
written as a contemporaneous record from the date above onward. It does not
purport to describe, retroactively certify, or reconstruct conditions prior to
that date.

---

## 1. What this project is

Northstar is a personal research and development project exploring a
declarative, specification-driven data platform architecture — ingestion,
modelling, and reporting pipelines on Microsoft Fabric and/or other cloud data platforms 
— applied to an upstream oil and gas production data domain, together with a demo insights web
application used to present the approach. It is undertaken independently of any
client engagement.

## 2. What this project is not

This repository does not contain, and is not derived from:

- source code belonging to any client or former client
- client configuration, deployment scripts, or environment definitions
- client data of any kind, including anonymised, sampled, masked, or
  synthetically derived-from-client data
- client business rules, domain models, naming conventions, or schemas
- any material identified as confidential by any client
- any material developed using client infrastructure, credentials, licences,
  or accounts

All customer-shaped material in this repository (naming conventions, example
configurations, sample dashboards) uses a generic placeholder identity
(`customer0`) and is not derived from, and does not represent, any real
customer or engagement.

All test and demonstration data in this repository is synthetic and generated
by scripts contained in this repository. See
`northstar-formation/models/customers/customer0/demo_data/nb_generate_dummy_bronze.Notebook`,
`northstar-formation/models/customers/customer0/demo_data/nb_generate_dummy_gold.Notebook`,
and the equivalent generators under
`northstar-deploy/configurations/customer0/versions/v1.0.0/data_engineering/demo_data/`.

## 3. Development conditions

- **Hardware:** Personally owned device; make/model and purchase details to be recorded if required.
- **Cloud resources:** Personally funded Microsoft Azure / Microsoft Fabric subscription; account or tenant reference available, with invoices retained.
- **Source hosting:** Personal GitHub account (`github.com/mmucapera`); repository `northstar`, created on the date recorded in the repository settings.
- **Git identity:** Commits authored under `mucapera@gmail.com`, distinct from the identity used for client work.
- **Working time:** Developed outside contracted working hours; commit timestamps reflect actual authoring times and have not been altered.

## 4. Technical basis

The architectural approach used here — declarative, specification-driven
generation of data platform artifacts (pipelines, semantic models, reports) —
is a generally available pattern documented in public vendor documentation,
published technical literature, and conference material. It is applied here to
an upstream oil and gas domain model developed independently for this project.


The author's prior academic work in this domain — MSc dissertation, Robert
Gordon University, 2016, on wellsite telemetry using the WITSML standard —
predates all client engagements referenced in this statement.


## Notes
- This file is updated if any of the above changes.