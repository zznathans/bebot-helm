## [1.3.1](https://github.com/zznathans/bebot-helm/compare/1.3.0...1.3.1) (2026-05-23)


### Bug Fixes

* **ci:** use global git config so gh-pages checkout can commit ([a186a22](https://github.com/zznathans/bebot-helm/commit/a186a229597bd1be0f43c34b9603abb13f39bbed)), closes [#pages](https://github.com/zznathans/bebot-helm/issues/pages) [#pages](https://github.com/zznathans/bebot-helm/issues/pages)

# [1.3.0](https://github.com/zznathans/bebot-helm/compare/1.2.5...1.3.0) (2026-05-23)


### Features

* **s3-backup:** pull credentials from dedicated external secret ([0b69fbb](https://github.com/zznathans/bebot-helm/commit/0b69fbb5f31f9de7db56b1fcbfee98115d14f6b8)), closes [#pages](https://github.com/zznathans/bebot-helm/issues/pages)

## [1.2.5](https://github.com/zznathans/bebot-helm/compare/1.2.4...1.2.5) (2026-05-23)


### Bug Fixes

* **deps:** update dependencies ([bd7a161](https://github.com/zznathans/bebot-helm/commit/bd7a1612e1ac75a4e4c01ee55774314c2637cb9a))

## [1.2.4](https://github.com/zznathans/bebot-helm/compare/1.2.3...1.2.4) (2026-05-18)


### Bug Fixes

* **pvc:** dont keep pvc on uninstall ([bad9376](https://github.com/zznathans/bebot-helm/commit/bad9376e33e1c56c83cde086df5437972dba8882))

## [1.2.3](https://github.com/zznathans/bebot-helm/compare/1.2.2...1.2.3) (2026-05-18)


### Bug Fixes

* **helm:** remove duplicate template ([529230f](https://github.com/zznathans/bebot-helm/commit/529230f5db6a97994423a7e57549d4dfc38da1eb))

## [1.2.2](https://github.com/zznathans/bebot-helm/compare/1.2.1...1.2.2) (2026-05-18)


### Bug Fixes

* **chart:** fix secret tool ([0f9a185](https://github.com/zznathans/bebot-helm/commit/0f9a18522ad651221983ff4c9d4a52783171ab21))

## [1.2.1](https://github.com/zznathans/bebot-helm/compare/1.2.0...1.2.1) (2026-05-18)


### Bug Fixes

* **helm:** add sync waves ([31aab7a](https://github.com/zznathans/bebot-helm/commit/31aab7a7f63aa4666cd272c47e092e2c10def62e))

# [1.2.0](https://github.com/zznathans/bebot-helm/compare/1.1.15...1.2.0) (2026-05-17)


### Features

* **bot:** simplify everything ([1ee5de1](https://github.com/zznathans/bebot-helm/commit/1ee5de147f674981bf6bca90865ed78787a87d53))

## [1.1.15](https://github.com/zznathans/bebot-helm/compare/1.1.14...1.1.15) (2026-05-09)


### Bug Fixes

* **ci:** double encoding ([8744c30](https://github.com/zznathans/bebot-helm/commit/8744c30375ee5478d2da64015dc38645a0339fe9))

## [1.1.14](https://github.com/zznathans/bebot-helm/compare/1.1.13...1.1.14) (2026-05-09)


### Bug Fixes

* **docs:** update readme ([4597bf6](https://github.com/zznathans/bebot-helm/commit/4597bf637835bb8b544d24c50d90bf2663e24135))

## [1.1.13](https://github.com/zznathans/bebot-helm/compare/1.1.12...1.1.13) (2026-05-09)


### Bug Fixes

* **helm:** bump release ([b094e37](https://github.com/zznathans/bebot-helm/commit/b094e37dbc77dc11f6ce5ed74bd9484207e5c885))
* prevent upload-sarif error when trivy scan fails before writing file ([45a9a02](https://github.com/zznathans/bebot-helm/commit/45a9a021ba46230c398157f2b4ec3f56162ee2c6))

## [1.1.12](https://github.com/zznathans/bebot-helm/compare/1.1.11...1.1.12) (2026-05-09)


### Bug Fixes

* **helm:** encode secrets ([8835cd1](https://github.com/zznathans/bebot-helm/commit/8835cd1120e61d2eaa7ecf1e886d8b7b340f0c9c))
* wire --print-to-stdout flag into argparse ([ffb6bf8](https://github.com/zznathans/bebot-helm/commit/ffb6bf8b1488b14e35b84c89f13db3c5e5a95f94))

## [1.1.11](https://github.com/zznathans/bebot-helm/compare/1.1.10...1.1.11) (2026-05-09)


### Bug Fixes

* **trivy:** configure trivy ([7ee8854](https://github.com/zznathans/bebot-helm/commit/7ee8854b06241ee5f7dba41d6a5ddbca6fa93762))

## [1.1.10](https://github.com/zznathans/bebot-helm/compare/1.1.9...1.1.10) (2026-05-06)


### Bug Fixes

* **mysqldump:** ignore lost+found ([dad2f9e](https://github.com/zznathans/bebot-helm/commit/dad2f9e7cc33f7d268dd59821b54970c7b7444f5))

## [1.1.9](https://github.com/zznathans/bebot-helm/compare/1.1.8...1.1.9) (2026-05-06)


### Bug Fixes

* **ci:** fix default aws image ([b78e285](https://github.com/zznathans/bebot-helm/commit/b78e285982c7ce46eb215985865f52ceff43fca4))

## [1.1.8](https://github.com/zznathans/bebot-helm/compare/1.1.7...1.1.8) (2026-05-05)


### Bug Fixes

* **aws:** fix aws cli image tag ([cd7c159](https://github.com/zznathans/bebot-helm/commit/cd7c159f77d54d1998483e84c4d4e8d481e2f6ef))

## [1.1.7](https://github.com/zznathans/bebot-helm/compare/1.1.6...1.1.7) (2026-05-05)


### Bug Fixes

* **ci:** fix secret name ([60ed7df](https://github.com/zznathans/bebot-helm/commit/60ed7dfa9b82c45fb2385ca6f2adeef6bc15f46e))

## [1.1.6](https://github.com/zznathans/bebot-helm/compare/1.1.5...1.1.6) (2026-05-05)


### Bug Fixes

* **ci:** fix secret keys ([52959c7](https://github.com/zznathans/bebot-helm/commit/52959c700b8ec7c9786878ce3f3252fb6c7e9731))

## [1.1.5](https://github.com/zznathans/bebot-helm/compare/1.1.4...1.1.5) (2026-05-05)


### Bug Fixes

* **mariadb:** fix backups ([6e8a8c7](https://github.com/zznathans/bebot-helm/commit/6e8a8c756718cf60f339810fd6818bafa719c666))

## [1.1.4](https://github.com/zznathans/bebot-helm/compare/1.1.3...1.1.4) (2026-05-05)


### Bug Fixes

* **ci:** hard shutdown ([72db9d9](https://github.com/zznathans/bebot-helm/commit/72db9d94615262fd5bf1f949e2c27b5f20986398))

## [1.1.3](https://github.com/zznathans/bebot-helm/compare/1.1.2...1.1.3) (2026-05-05)


### Bug Fixes

* **ci:** branch ([7038752](https://github.com/zznathans/bebot-helm/commit/7038752aa722dcae78385702784f5b259390b0fa))
* **helm:** pvc adjustments ([cc20f29](https://github.com/zznathans/bebot-helm/commit/cc20f295c3ff1cf9f997344bcf34b3f2727c935c))

## [1.1.2](https://github.com/zznathans/bebot-helm/compare/1.1.1...1.1.2) (2026-05-05)


### Bug Fixes

* **ci:** helm docs ([7ff22e9](https://github.com/zznathans/bebot-helm/commit/7ff22e9f3952382ba35ee330b1bbbc6031274da3))
* **helm:** update templates ([2c0f422](https://github.com/zznathans/bebot-helm/commit/2c0f422ac36cb00b183ffb83b9e4b410e71db476))

## [1.1.1](https://github.com/zznathans/bebot-helm/compare/1.1.0...1.1.1) (2026-05-05)


### Bug Fixes

* **github:** release ([c4e64f5](https://github.com/zznathans/bebot-helm/commit/c4e64f50df73c945d1bd0bd1a27507854ad2e835))

# [1.1.0](https://github.com/zznathans/bebot-helm/compare/1.0.9...1.1.0) (2026-04-28)


### Bug Fixes

* **ci:** bump ([549f6db](https://github.com/zznathans/bebot-helm/commit/549f6db6ec462a050081d0ea689693eac5225361))


### Features

* **tests, docs:** add tests ([55e38af](https://github.com/zznathans/bebot-helm/commit/55e38af6f6cdfeb5d829dbfff8c5f47885883f53))
* **tests, docs:** add tests ([76d3947](https://github.com/zznathans/bebot-helm/commit/76d3947d6e575a98d3c15ce17ea1ebaa58668891))

## [1.0.9](https://github.com/zznathans/bebot-helm/compare/1.0.8...1.0.9) (2026-04-28)


### Bug Fixes

* **metrics:** add servicemonitor ([43a3d60](https://github.com/zznathans/bebot-helm/commit/43a3d6015b5e643c3eca916fb9825d00eb766743))

## [1.0.8](https://github.com/zznathans/bebot-helm/compare/1.0.7...1.0.8) (2026-04-28)


### Bug Fixes

* **docker, metrics:** fix image build ([292c5d1](https://github.com/zznathans/bebot-helm/commit/292c5d1a728bb5f14cdd99023f3f33c637682d79))

## [1.0.7](https://github.com/zznathans/bebot-helm/compare/1.0.6...1.0.7) (2026-04-28)


### Bug Fixes

* **ci:** wait for mysql to be up before starting metrics ([b96a7e0](https://github.com/zznathans/bebot-helm/commit/b96a7e075c99896e19baebe042525856a36d3397))

## [1.0.6](https://github.com/zznathans/bebot-helm/compare/1.0.5...1.0.6) (2026-04-28)


### Bug Fixes

* **docker:** pin image name ([d9e6b93](https://github.com/zznathans/bebot-helm/commit/d9e6b9302b8d8e43c482ff677046dbecf0d0e72b))

## [1.0.5](https://github.com/zznathans/bebot-helm/compare/1.0.4...1.0.5) (2026-04-28)


### Bug Fixes

* **mariadb:** add metrics ([5f7eb3c](https://github.com/zznathans/bebot-helm/commit/5f7eb3cdcf08dccee4c15562422897caba71cca6))

## [1.0.4](https://github.com/zznathans/bebot-helm/compare/1.0.3...1.0.4) (2026-04-28)


### Bug Fixes

* **ci:** bump release ([b16c033](https://github.com/zznathans/bebot-helm/commit/b16c033a04aea965e3ca8323f73c32b04b25f9ef))

## [1.0.3](https://github.com/zznathans/bebot-helm/compare/1.0.2...1.0.3) (2026-04-25)


### Bug Fixes

* **ci:** bump release ([4d659b4](https://github.com/zznathans/bebot-helm/commit/4d659b48dde9322d66779155915383ced66a8559))

## [1.0.2](https://github.com/zznathans/bebot-helm/compare/1.0.1...1.0.2) (2026-04-12)


### Bug Fixes

* **ci:** release ([76178e5](https://github.com/zznathans/bebot-helm/commit/76178e59ad969dbe10dbdf23948c0fc8c0bfa865))

## [1.0.1](https://github.com/zznathans/bebot-helm/compare/1.0.0...1.0.1) (2026-04-12)


### Bug Fixes

* **release:** trigger release ([f45bf7f](https://github.com/zznathans/bebot-helm/commit/f45bf7fd6abfc15a3c7e5caa456af6319645cc23))

# 1.0.0 (2026-04-12)


### Bug Fixes

* **dependabot:** fix dir ([64c7f40](https://github.com/zznathans/bebot-helm/commit/64c7f40bf1db86ae9bd92947402d28f982cc0b52))

## [1.0.17](https://github.com/zznathans/bebot-helm/compare/1.0.16...1.0.17) (2026-04-12)


### Bug Fixes

* **mysql:** init container ([98c788c](https://github.com/zznathans/bebot-helm/commit/98c788c107477c4274491e76ca75a2f28de237ee))

## [1.0.16](https://github.com/zznathans/bebot-helm/compare/1.0.15...1.0.16) (2026-04-12)


### Bug Fixes

* **mysql:** wait for secret ([4898692](https://github.com/zznathans/bebot-helm/commit/48986926b9727246f2c69fa2fdf41ee854b4ee91))

## [1.0.15](https://github.com/zznathans/bebot-helm/compare/1.0.14...1.0.15) (2026-04-12)


### Bug Fixes

* **mysql:** fix ([1a53783](https://github.com/zznathans/bebot-helm/commit/1a5378374721aba3f8a13bb6070bfe58db6ea094))

## [1.0.14](https://github.com/zznathans/bebot-helm/compare/1.0.13...1.0.14) (2026-04-12)


### Bug Fixes

* **mysql:** add missing keys ([addc595](https://github.com/zznathans/bebot-helm/commit/addc5953f5e64bd5114f5f26bfd95fdc031b85ac))

## [1.0.13](https://github.com/zznathans/bebot-helm/compare/1.0.12...1.0.13) (2026-04-12)


### Bug Fixes

* **mysql:** use hook ([6a3f3f7](https://github.com/zznathans/bebot-helm/commit/6a3f3f72acc187756daa59a995d54edc4f42a158))

## [1.0.12](https://github.com/zznathans/bebot-helm/compare/1.0.11...1.0.12) (2026-04-11)


### Bug Fixes

* **docker:** refactor dockerfile ([cd81acb](https://github.com/zznathans/bebot-helm/commit/cd81acbecfd2adaa3ec4a79705da09d93b414bef))

## [1.0.11](https://github.com/zznathans/bebot-helm/compare/1.0.10...1.0.11) (2026-04-11)


### Bug Fixes

* **readme:** update readme with missile values ([a9f14ca](https://github.com/zznathans/bebot-helm/commit/a9f14ca55c02bc8f0d5dbcdb126d092ca7dc7503))

## [1.0.10](https://github.com/zznathans/bebot-helm/compare/1.0.9...1.0.10) (2026-04-11)


### Bug Fixes

* **ci:** release ([24b0f86](https://github.com/zznathans/bebot-helm/commit/24b0f8677f9ee4035efdc2de5b6337914879994e))

## [1.0.9](https://github.com/zznathans/bebot-helm/compare/1.0.8...1.0.9) (2026-04-11)


### Bug Fixes

* **ci:** fix ([e8013b0](https://github.com/zznathans/bebot-helm/commit/e8013b01ab95e793880a6856cf744a91ccf6f734))

## [1.0.8](https://github.com/zznathans/bebot-helm/compare/1.0.7...1.0.8) (2026-04-11)


### Bug Fixes

* **ci:** fix branch ([4b285a5](https://github.com/zznathans/bebot-helm/commit/4b285a570be187513ec27b07eb037db00da40a1e))

## [1.0.7](https://github.com/zznathans/bebot-helm/compare/1.0.6...1.0.7) (2026-04-11)


### Bug Fixes

* **ci:** fix branch ([5a3da83](https://github.com/zznathans/bebot-helm/commit/5a3da835edf4eff6beb487e73d91f88a2ffb8843))

## [1.0.6](https://github.com/zznathans/bebot-helm/compare/1.0.5...1.0.6) (2026-04-11)


### Bug Fixes

* **ci:** on release ([4573b5e](https://github.com/zznathans/bebot-helm/commit/4573b5e141b73ed5f6b034a395ce4effa377343a))

## [1.0.5](https://github.com/zznathans/bebot-helm/compare/1.0.4...1.0.5) (2026-04-11)


### Bug Fixes

* **ci:** fix path ([9eea9b8](https://github.com/zznathans/bebot-helm/commit/9eea9b828550fc138fe199db2539f9df27f5fde5))

## [1.0.4](https://github.com/zznathans/bebot-helm/compare/1.0.3...1.0.4) (2026-04-11)


### Bug Fixes

* **ci:** bump version ([2bc9923](https://github.com/zznathans/bebot-helm/commit/2bc9923842f395ab4f7368b923d47a388a0f14e6))

## [1.0.3](https://github.com/zznathans/bebot-helm/compare/1.0.2...1.0.3) (2026-04-11)


### Bug Fixes

* **ci:** fix ([d623c39](https://github.com/zznathans/bebot-helm/commit/d623c396326283b045761ad40f5e2f1b5331a567))

## [1.0.2](https://github.com/zznathans/bebot-helm/compare/1.0.1...1.0.2) (2026-04-11)


### Bug Fixes

* **ci:** adjust ci jobs ([#3](https://github.com/zznathans/bebot-helm/issues/3)) ([3a28356](https://github.com/zznathans/bebot-helm/commit/3a28356934a6407be55aa5dd8374fa1960574ec6))
* **ci:** fix ([b903139](https://github.com/zznathans/bebot-helm/commit/b903139195cd925812097b4dc1ecea40b35800ae))
* **helm:** fix chart path ([8989a5c](https://github.com/zznathans/bebot-helm/commit/8989a5cacaecd22b5327d8551bdfa7d6db53c959))

## [1.0.1](https://github.com/zznathans/bebot-helm/compare/1.0.0...1.0.1) (2026-04-11)


### Bug Fixes

* **helm:** bump ([9cb8236](https://github.com/zznathans/bebot-helm/commit/9cb8236c5c4c997d422d4901922b38f9c4c18e1f))

# 1.0.0 (2026-04-11)


### Features

* **release:** release ([8cfee24](https://github.com/zznathans/bebot-helm/commit/8cfee24881e8fa17a88ee170bd2d6ef79e2d4e5b))
