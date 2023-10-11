TODO
====

Infra
-----
- ? add helm chart
- ? add kustomize support

Code
----
- add proper error handling
- ensure proper request timeout handling
- add tests

Features
--------
- Holistic target choice
- Better scheduler that won't move instance back and forth
- find/compose more suitable metric for load
  which is independent of number of cores
- each CR watches over subset of compute nodes, allowing to
  model AZs/aggregates mirroring those in Nova.
- return some results to status of CR
