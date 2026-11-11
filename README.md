# README

[![OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndt-overwatch/ospo-compliance.svg)](tools/governance-report/README.md)
[![Days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndt-overwatch/develop-activity.svg)](tools/governance-report/README.md)
[![Last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndt-overwatch/last-checked.svg)](tools/governance-report/README.md)

The central weekly scan publishes status-only badges for every included repository, public and private, to the
`sync/governance-badges` branch. Badges show the latest saved check, not live results; `not checked` means no
completed scan is within the freshness window. Full reports remain separate workflow artifacts.

## Public repository governance

The table below moves the public-repository overview from the organisation profile to this central report repository. The per-repository badges are currently based only on scans of each repository's `develop` branch; a repository without `develop` is shown as unknown/not checked rather than silently scanned on `main`. We may move this baseline to `main` later.

The **Days since last commit to Develop** badge is intentionally gray for every value and shows elapsed whole days; it does not use red/amber/green status colors. The **Last checked** badge still indicates report freshness.

The **OSPO compliance** badge is based on the governance files, templates, Dependabot configuration and PR age, verified credential scan, SBOM, automatic branch deletion, Dependabot auto-merge state, workflow synchronization, and main-to-develop back-merge checks. It does **not** include days since the last Develop commit or scan freshness.

| Repository | OSPO compliance | Days since last commit to Develop | Last checked |
| --- | --- | --- | --- |
| [archetypes](https://github.com/National-Node-Net/archetypes) | ![archetypes OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/archetypes/ospo-compliance.svg) | ![archetypes days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/archetypes/develop-activity.svg) | ![archetypes last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/archetypes/last-checked.svg) |
| [data-extractor](https://github.com/National-Node-Net/data-extractor) | ![data-extractor OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/data-extractor/ospo-compliance.svg) | ![data-extractor days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/data-extractor/develop-activity.svg) | ![data-extractor last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/data-extractor/last-checked.svg) |
| [federator](https://github.com/National-Node-Net/federator) | ![federator OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/federator/ospo-compliance.svg) | ![federator days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/federator/develop-activity.svg) | ![federator last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/federator/last-checked.svg) |
| [federator-certificate-manager](https://github.com/National-Node-Net/federator-certificate-manager) | ![federator-certificate-manager OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/federator-certificate-manager/ospo-compliance.svg) | ![federator-certificate-manager days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/federator-certificate-manager/develop-activity.svg) | ![federator-certificate-manager last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/federator-certificate-manager/last-checked.svg) |
| [fuseki-yaml-config](https://github.com/National-Node-Net/fuseki-yaml-config) | ![fuseki-yaml-config OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/fuseki-yaml-config/ospo-compliance.svg) | ![fuseki-yaml-config days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/fuseki-yaml-config/develop-activity.svg) | ![fuseki-yaml-config last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/fuseki-yaml-config/last-checked.svg) |
| [graphql-jena](https://github.com/National-Node-Net/graphql-jena) | ![graphql-jena OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/graphql-jena/ospo-compliance.svg) | ![graphql-jena days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/graphql-jena/develop-activity.svg) | ![graphql-jena last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/graphql-jena/last-checked.svg) |
| [helm-charts](https://github.com/National-Node-Net/helm-charts) | ![helm-charts OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/helm-charts/ospo-compliance.svg) | ![helm-charts days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/helm-charts/develop-activity.svg) | ![helm-charts last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/helm-charts/last-checked.svg) |
| [ianode-access](https://github.com/National-Node-Net/ianode-access) | ![ianode-access OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ianode-access/ospo-compliance.svg) | ![ianode-access days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ianode-access/develop-activity.svg) | ![ianode-access last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ianode-access/last-checked.svg) |
| [jena-fuseki-kafka](https://github.com/National-Node-Net/jena-fuseki-kafka) | ![jena-fuseki-kafka OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/jena-fuseki-kafka/ospo-compliance.svg) | ![jena-fuseki-kafka days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/jena-fuseki-kafka/develop-activity.svg) | ![jena-fuseki-kafka last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/jena-fuseki-kafka/last-checked.svg) |
| [jwt-servlet-auth](https://github.com/National-Node-Net/jwt-servlet-auth) | ![jwt-servlet-auth OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/jwt-servlet-auth/ospo-compliance.svg) | ![jwt-servlet-auth days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/jwt-servlet-auth/develop-activity.svg) | ![jwt-servlet-auth last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/jwt-servlet-auth/last-checked.svg) |
| [label-builder](https://github.com/National-Node-Net/label-builder) | ![label-builder OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/label-builder/ospo-compliance.svg) | ![label-builder days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/label-builder/develop-activity.svg) | ![label-builder last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/label-builder/last-checked.svg) |
| [management-node](https://github.com/National-Node-Net/management-node) | ![management-node OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/management-node/ospo-compliance.svg) | ![management-node days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/management-node/develop-activity.svg) | ![management-node last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/management-node/last-checked.svg) |
| [ndt-data-catalogue](https://github.com/National-Node-Net/ndt-data-catalogue) | ![ndt-data-catalogue OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndt-data-catalogue/ospo-compliance.svg) | ![ndt-data-catalogue days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndt-data-catalogue/develop-activity.svg) | ![ndt-data-catalogue last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndt-data-catalogue/last-checked.svg) |
| [ndt-overwatch](https://github.com/National-Node-Net/ndt-overwatch) | ![ndt-overwatch OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndt-overwatch/ospo-compliance.svg) | ![ndt-overwatch days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndt-overwatch/develop-activity.svg) | ![ndt-overwatch last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndt-overwatch/last-checked.svg) |
| [ndtp-component-library](https://github.com/National-Node-Net/ndtp-component-library) | ![ndtp-component-library OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndtp-component-library/ospo-compliance.svg) | ![ndtp-component-library days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndtp-component-library/develop-activity.svg) | ![ndtp-component-library last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ndtp-component-library/last-checked.svg) |
| [node-lib](https://github.com/National-Node-Net/node-lib) | ![node-lib OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/node-lib/ospo-compliance.svg) | ![node-lib days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/node-lib/develop-activity.svg) | ![node-lib last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/node-lib/last-checked.svg) |
| [ospo-resources](https://github.com/National-Node-Net/ospo-resources) | ![ospo-resources OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ospo-resources/ospo-compliance.svg) | ![ospo-resources days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ospo-resources/develop-activity.svg) | ![ospo-resources last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/ospo-resources/last-checked.svg) |
| [rdf-abac](https://github.com/National-Node-Net/rdf-abac) | ![rdf-abac OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/rdf-abac/ospo-compliance.svg) | ![rdf-abac days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/rdf-abac/develop-activity.svg) | ![rdf-abac last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/rdf-abac/last-checked.svg) |
| [rdf-pbac](https://github.com/National-Node-Net/rdf-pbac) | ![rdf-pbac OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/rdf-pbac/ospo-compliance.svg) | ![rdf-pbac days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/rdf-pbac/develop-activity.svg) | ![rdf-pbac last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/rdf-pbac/last-checked.svg) |
| [secure-agent-graph](https://github.com/National-Node-Net/secure-agent-graph) | ![secure-agent-graph OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/secure-agent-graph/ospo-compliance.svg) | ![secure-agent-graph days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/secure-agent-graph/develop-activity.svg) | ![secure-agent-graph last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/secure-agent-graph/last-checked.svg) |
| [secure-agents-lib](https://github.com/National-Node-Net/secure-agents-lib) | ![secure-agents-lib OSPO compliance](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/secure-agents-lib/ospo-compliance.svg) | ![secure-agents-lib days since last commit to Develop](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/secure-agents-lib/develop-activity.svg) | ![secure-agents-lib last checked](https://raw.githubusercontent.com/National-Node-Net/ndt-overwatch/sync/governance-badges/repositories/secure-agents-lib/last-checked.svg) |

**Repository:** `ndt-overwatch`  
**Description:** `The ndt-overwatch repository serves as the central hub for executing organisation-wide automations across the National Digital Twin Programme (NDTP). It houses automated workflows and scripts designed to enforce governance standards, gather compliance metrics, and streamline administrative tasks.`  
**SPDX-License-Identifier:** `Apache-2.0 AND OGL-UK-3.0`

## Overview

The NDTP Open Source Program Office (OSPO) use this repository as a dedicated location to manage and execute organisation-wide governance and utility automations across the National Digital Twin Programme (NDTP). Future use cases include gathering compliance reports and testing metrics, enhancing efficiency, reducing manual effort, and promoting consistency in how governance is applied throughout the Programme.

## Prerequisites

The contents maintained in this repository are designed for use with GitHub.

## Features

### Supplier Register Generation

An automated process to generate a consolidated, de-duplicated register of supplier organisations acknowledged across our public repositories. This register is derived from the `ACKNOWLEDGEMENTS.md` files in each repository and provides a single reference point for reporting and governance purposes.

### Organisation Governance Report

The `OSPO governance report` workflow scans active organisation repositories and produces Markdown, HTML, and JSON dashboards covering governance files, templates, Dependabot policy and pull requests, releases and SBOMs, repository settings, activity, workflow status, and verified TruffleHog findings. It runs weekly and can be dispatched manually after the workflow is available on the default branch. See [`tools/governance-report/README.md`](tools/governance-report/README.md) for check definitions, permissions, and manual-run guidance.

## Public Funding Acknowledgment

This repository has been developed with public funding as part of the National Digital Twin Programme (NDTP), a UK Government initiative. NDTP, alongside its partners, has invested in this work to advance open, secure, and reusable digital twin technologies for any organisation, whether from the public or private sector, irrespective of size.  

## License

This repository contains both source code and documentation, which are covered by different licenses:

- **Code:** Originally developed by the National Digital Twin Programme Open-Source Program Office for the National Digital Twin Programme. Licensed under the [Apache License 2.0](./LICENSE.md).
- **Documentation:** Licensed under the [Open Government Licence v3.0](./OGL_LICENSE.md).
  
See `LICENSE.md`, `OGL_LICENSE.md`, and `NOTICE.md` for details.

## Security and Responsible Disclosure

We take security seriously. If you believe you have found a security vulnerability in this repository, please follow our responsible disclosure process outlined in `SECURITY.md`.

## Software Bill of Materials (SBOM)

This project provides a Software Bill of Materials (SBOM) to help users and integrators understand its dependencies.

### Current SBOM

Download the [latest SBOM for this codebase](https://github.com/National-Node-Net/ndt-overwatch/dependency-graph/sbom) to view the current list of components used in this repository.

## Contributing

We welcome contributions that align with the Programme’s objectives. Please read our `CONTRIBUTING.md` guidelines before submitting pull requests.

## Acknowledgements

This repository has benefited from collaboration with various organisations. For a list of acknowledgments, see `ACKNOWLEDGEMENTS.md`.

## Support and Contact

For questions or support, check our Issues or contact the NDTP team on <ndtp@businessandtrade.gov.uk>.

**Maintained by the National Digital Twin Programme (NDTP).**

© Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.
