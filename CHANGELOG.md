# Changelog

## [0.19.2](https://github.com/peterprescott/freckle/compare/v0.19.1...v0.19.2) (2026-01-30)


### Bug Fixes

* prevent secret scanner matching across lines ([#84](https://github.com/peterprescott/freckle/issues/84)) ([d81d042](https://github.com/peterprescott/freckle/commit/d81d042087ab8a5a3411349cd4c040e8f57361a4))

## [0.19.1](https://github.com/peterprescott/freckle/compare/v0.19.0...v0.19.1) (2026-01-30)


### Bug Fixes

* install tools in parallel with --all flag ([#82](https://github.com/peterprescott/freckle/issues/82)) ([c83eac0](https://github.com/peterprescott/freckle/commit/c83eac0a2a54b4f650897549c846daf828d56552))

## [0.19.0](https://github.com/peterprescott/freckle/compare/v0.18.2...v0.19.0) (2026-01-28)


### Features

* add push command, remove auto-push from save ([1d858a3](https://github.com/peterprescott/freckle/commit/1d858a31f71281e4ecf772876212741b9104fe91))
* branches authoritative for profile resolution ([511a23f](https://github.com/peterprescott/freckle/commit/511a23f5a3274782cd719ba97a413128067444bf))
* doctor checks for profile/branch alignment ([4ea2dc4](https://github.com/peterprescott/freckle/commit/4ea2dc49d162f4167d69fc5046dafc50c80515ed))
* enhanced doctor with comprehensive branch analysis ([854905c](https://github.com/peterprescott/freckle/commit/854905c57bed8cdbc2c2d66604dd859918d206c2))

## [0.18.2](https://github.com/peterprescott/freckle/compare/v0.18.1...v0.18.2) (2026-01-28)


### Bug Fixes

* auto-clone dotfiles when config exists but repo not cloned ([#77](https://github.com/peterprescott/freckle/issues/77)) ([89de9d9](https://github.com/peterprescott/freckle/commit/89de9d9d56697fabf74b3f3770cc1585873de6bc))

## [0.18.1](https://github.com/peterprescott/freckle/compare/v0.18.0...v0.18.1) (2026-01-28)


### Bug Fixes

* use git add -u instead of git add -A in save command ([#75](https://github.com/peterprescott/freckle/issues/75)) ([39bfd95](https://github.com/peterprescott/freckle/commit/39bfd9526318df42b2726acbb94667e12f0a2ed9))

## [0.18.0](https://github.com/peterprescott/freckle/compare/v0.17.0...v0.18.0) (2026-01-28)


### Features

* add profile inheritance with include/exclude ([#72](https://github.com/peterprescott/freckle/issues/72)) ([45833cb](https://github.com/peterprescott/freckle/commit/45833cbae50b8ef31dd939c1c174ca23bc5ecea1))


### Documentation

* update README config example for profile inheritance ([#74](https://github.com/peterprescott/freckle/issues/74)) ([339411e](https://github.com/peterprescott/freckle/commit/339411e3be48850a1e7ebbabe929d448518701bd))

## [0.17.0](https://github.com/peterprescott/freckle/compare/v0.16.0...v0.17.0) (2026-01-28)


### Features

* add consistent colorized output using Rich ([#58](https://github.com/peterprescott/freckle/issues/58)) ([a05f9dc](https://github.com/peterprescott/freckle/commit/a05f9dc31e6358daa342391ce88577cffde09815))

## [0.16.0](https://github.com/peterprescott/freckle/compare/v0.15.1...v0.16.0) (2026-01-28)


### Features

* add freckle config open &lt;tool&gt; command ([#54](https://github.com/peterprescott/freckle/issues/54)) ([ed87416](https://github.com/peterprescott/freckle/commit/ed874167952d99b10c7153eae327ff6954bd71c7))

## [0.15.1](https://github.com/peterprescott/freckle/compare/v0.15.0...v0.15.1) (2026-01-28)


### Performance Improvements

* parallelize tool verification in freckle status ([#51](https://github.com/peterprescott/freckle/issues/51)) ([2d42c57](https://github.com/peterprescott/freckle/commit/2d42c57832570f9af956e42a835f19b52bdfcc3a))

## [0.15.0](https://github.com/peterprescott/freckle/compare/v0.14.0...v0.15.0) (2026-01-28)


### Features

* support freckle history freckle ([#49](https://github.com/peterprescott/freckle/issues/49)) ([481ab27](https://github.com/peterprescott/freckle/commit/481ab27bc9c39fdda78896f22c507af599e58d21))

## [0.14.0](https://github.com/peterprescott/freckle/compare/v0.13.0...v0.14.0) (2026-01-28)


### Features

* support .freckle.yml config filename ([#47](https://github.com/peterprescott/freckle/issues/47)) ([8a12bbe](https://github.com/peterprescott/freckle/commit/8a12bbe217b77d706dfaeeb2a24f0304e4568903))

## [0.13.0](https://github.com/peterprescott/freckle/compare/v0.12.1...v0.13.0) (2026-01-28)


### Features

* add history, restore, and diff commands for dotfile time-travel ([#45](https://github.com/peterprescott/freckle/issues/45)) ([56b3cc0](https://github.com/peterprescott/freckle/commit/56b3cc01b74610a2628ae6ad218f45bd973c2f66))

## [0.12.1](https://github.com/peterprescott/freckle/compare/v0.12.0...v0.12.1) (2026-01-27)


### Bug Fixes

* doctor only checks tools for current profile ([#43](https://github.com/peterprescott/freckle/issues/43)) ([5df93a3](https://github.com/peterprescott/freckle/commit/5df93a3775e4e1f681deb8d92c6a79e4e28cc8e9))

## [0.12.0](https://github.com/peterprescott/freckle/compare/v0.11.1...v0.12.0) (2026-01-27)


### Features

* add `freckle tools config` command to open tool configs ([#41](https://github.com/peterprescott/freckle/issues/41)) ([3210c9e](https://github.com/peterprescott/freckle/commit/3210c9ed810754adf27d06f146983f99bad5c062))

## [0.11.0](https://github.com/peterprescott/freckle/compare/v0.10.2...v0.11.0) (2026-01-27)


### Features

* add propagate command to copy files across branches ([#39](https://github.com/peterprescott/freckle/issues/39)) ([84c0a98](https://github.com/peterprescott/freckle/commit/84c0a98213720e6431296dc377176bdcd2917cc9))

## [0.10.2](https://github.com/peterprescott/freckle/compare/v0.10.1...v0.10.2) (2026-01-27)


### Bug Fixes

* doctor checks config alignment across profile branches ([#36](https://github.com/peterprescott/freckle/issues/36)) ([21775e7](https://github.com/peterprescott/freckle/commit/21775e7de9da6a3f0a16dcc56a78619b8ee14b17))
* doctor suggests config propagate instead of backup ([#38](https://github.com/peterprescott/freckle/issues/38)) ([ea1de16](https://github.com/peterprescott/freckle/commit/ea1de16591e7ff8aeaa97cef5f52569aa80590e5))

## [0.10.1](https://github.com/peterprescott/freckle/compare/v0.10.0...v0.10.1) (2026-01-27)


### Bug Fixes

* config editor double-open and auto-propagate config on backup ([#25](https://github.com/peterprescott/freckle/issues/25)) ([641c688](https://github.com/peterprescott/freckle/commit/641c6888699850aef190a62979ee9ea8a5d20ab8))
* get_dotfiles_manager detects actual git branch ([#28](https://github.com/peterprescott/freckle/issues/28)) ([12c104a](https://github.com/peterprescott/freckle/commit/12c104a7f1bbfaf1767acbfa0d892dd5457d071b))

## [0.10.1](https://github.com/peterprescott/freckle/compare/v0.10.0...v0.10.1) (2026-01-27)


### Bug Fixes

* config editor double-open and auto-propagate config on backup ([#25](https://github.com/peterprescott/freckle/issues/25)) ([12a0ae9](https://github.com/peterprescott/freckle/commit/12a0ae92e9c9e7dfff06b92be3950e91ba62ab89))

## [0.10.0](https://github.com/peterprescott/freckle/compare/v0.9.2...v0.10.0) (2026-01-27)


### Features

* add version check to doctor and upgrade command ([#23](https://github.com/peterprescott/freckle/issues/23)) ([2d305af](https://github.com/peterprescott/freckle/commit/2d305af3a7f8df849e8d264f7d0f8d34709edac6))

## [0.9.2](https://github.com/peterprescott/freckle/compare/v0.9.1...v0.9.2) (2026-01-27)


### Bug Fixes

* status shows actual git branch, profile create pushes to remote ([#21](https://github.com/peterprescott/freckle/issues/21)) ([66d1721](https://github.com/peterprescott/freckle/commit/66d17213e00a32efc0c91eafba3ca24d7a7ba78f))

## [0.9.1](https://github.com/peterprescott/freckle/compare/v0.9.0...v0.9.1) (2026-01-27)


### Bug Fixes

* use shell=True for verify commands ([#19](https://github.com/peterprescott/freckle/issues/19)) ([ce1e735](https://github.com/peterprescott/freckle/commit/ce1e73511772b45ddbef8458da57682b827b8c46))

## [0.9.0](https://github.com/peterprescott/freckle/compare/v0.8.1...v0.9.0) (2026-01-27)


### Features

* filter tools by active profile modules ([#15](https://github.com/peterprescott/freckle/issues/15)) ([faac9e8](https://github.com/peterprescott/freckle/commit/faac9e801c2e2a9c3fb846375bd6b69e1c92d575))

## [0.8.1](https://github.com/peterprescott/freckle/compare/v0.8.0...v0.8.1) (2026-01-27)


### Bug Fixes

* extract PR number from release-please output JSON ([#13](https://github.com/peterprescott/freckle/issues/13)) ([a6358c9](https://github.com/peterprescott/freckle/commit/a6358c91c7d6e99cd6771c2c4664485b659a294d))

## [0.8.0](https://github.com/peterprescott/freckle/compare/v0.7.1...v0.8.0) (2026-01-27)


### Features

* add curated install scripts for more tools ([#11](https://github.com/peterprescott/freckle/issues/11)) ([9d2ba16](https://github.com/peterprescott/freckle/commit/9d2ba16ec7dd4e1a3cc8c553c212103aa8bbe2a5))

## [0.7.1](https://github.com/peterprescott/freckle/compare/v0.7.0...v0.7.1) (2026-01-27)


### Bug Fixes

* script installation TypeError ([#8](https://github.com/peterprescott/freckle/issues/8)) ([ba81531](https://github.com/peterprescott/freckle/commit/ba8153120789fa7947f05550e1c984fa254f837f))

## [0.7.0](https://github.com/peterprescott/freckle/compare/v0.6.0...v0.7.0) (2026-01-27)


### Features

* add --all flag to install all missing tools ([#3](https://github.com/peterprescott/freckle/issues/3)) ([deb0012](https://github.com/peterprescott/freckle/commit/deb00125e6bf9df5a76b070f8e50f439df92b231))
* add bootstrap script for fresh system setup ([ee1e84a](https://github.com/peterprescott/freckle/commit/ee1e84a5d6064789d34f7a4e5539b8891d13fd04))
* add bootstrap script for fresh system setup ([31fde0d](https://github.com/peterprescott/freckle/commit/31fde0d06c272f4c70cb0bfff203c8a9a33dafb3))


### Bug Fixes

* CI failures and TypedDict return types ([51c55df](https://github.com/peterprescott/freckle/commit/51c55dfce58629ef17b8d0d628dd6b88c76e62e3))
* type annotations for TypedDict returns ([3347811](https://github.com/peterprescott/freckle/commit/3347811458f562c1afd4b7499360628e048ff8d2))
* use explicit --initial-branch=main in test setup ([d856aa1](https://github.com/peterprescott/freckle/commit/d856aa10e388a847f76a9cfd18bfadf53ff46b20))
