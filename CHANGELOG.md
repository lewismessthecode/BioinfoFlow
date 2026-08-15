# Changelog

All notable user-facing changes to Bioinfoflow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
while it remains under active pre-1.0 development.

## [0.3.0](https://github.com/lewismessthecode/BioinfoFlow/compare/0.2.0...0.3.0) (2026-08-14)

### New Features

- Added a composer context-usage meter so agent sessions can show how much
  context has been consumed during a turn ([429ef1b](https://github.com/lewismessthecode/BioinfoFlow/commit/429ef1bee529e62f96a9a827a46ae1bd043d5391)).
- Added automatic remote selection for agent tools when a workflow target is
  not explicitly pinned ([#221](https://github.com/lewismessthecode/BioinfoFlow/issues/221)) ([1eadcfd](https://github.com/lewismessthecode/BioinfoFlow/commit/1eadcfd9ea06dfe701970251a2c3193b152eedf9)).

### Changed

- Replaced the legacy Agent Core with a complete Agent Harness. The new
  runtime consolidates durable sessions and runs, workspace execution,
  sandboxed tools, recovery, agent tokens, and refreshed API and CLI contracts
  ([6ed4502](https://github.com/lewismessthecode/BioinfoFlow/commit/6ed4502ef1de0d40aec0b1ad70c8e89d2cd4d780)).
- Made the local installer seed native skills in empty install directories and
  report download progress while it runs ([e79eb7b](https://github.com/lewismessthecode/BioinfoFlow/commit/e79eb7b5425d8f4da6ffff9cbc99869c5ea92839), [3af2165](https://github.com/lewismessthecode/BioinfoFlow/commit/3af2165e25014bd1681b8e0e07fed06be3dab292)).

### Fixed

- Allowed scoped agent file commands ([50495ce](https://github.com/lewismessthecode/BioinfoFlow/commit/50495ce23e33e453b926c25b3d368789c718c541)).
- Finished agent runtime leases during shutdown ([1a98c94](https://github.com/lewismessthecode/BioinfoFlow/commit/1a98c941b73a3a7de4d0b6e1e3e9a4ebbc9ac4c5)).
- Preserved agent streaming when promoting a conversation ([3c59010](https://github.com/lewismessthecode/BioinfoFlow/commit/3c590105369955f9af0fe2915c7275bc202069a1)).
- Restored Linux agent tool reliability ([c228808](https://github.com/lewismessthecode/BioinfoFlow/commit/c228808d0a60ae988735226dce860e0a1a3e9bef)).
- Made the agent demo's first run deterministic ([6f1ac83](https://github.com/lewismessthecode/BioinfoFlow/commit/6f1ac83852e6b18a08c645e20ba705263d80610b)).
- Avoided duplicate scheduler startup recovery ([b1ddf88](https://github.com/lewismessthecode/BioinfoFlow/commit/b1ddf8864b709771a2863de2fd53d5ad15e44cd7)).
- Polished the runs table and celebration motion ([0abfb36](https://github.com/lewismessthecode/BioinfoFlow/commit/0abfb36e7ecfa54aad29e3921f53855798c24123)).
- Enforced localized connection-skill copy in the frontend ([873dbe6](https://github.com/lewismessthecode/BioinfoFlow/commit/873dbe6c583c8fbb36c66b53fb33149d03f167b5)).

### Security

- Blocked sensitive paths from agent context resolution ([c0c51e4](https://github.com/lewismessthecode/BioinfoFlow/commit/c0c51e490dc2db4547472987255dcdfa17cf5564)).
- Hardened monitoring and upload endpoints with shared upload limits and
  stronger access checks ([348d313](https://github.com/lewismessthecode/BioinfoFlow/commit/348d3134bc5026641c109d117a128c1fedbbfd6b)).
- Hardened notification delivery and SSRF protections ([0b311d7](https://github.com/lewismessthecode/BioinfoFlow/commit/0b311d72756e8f5d0758c7ff202e8329c028f612)).

## [0.2.0](https://github.com/lewismessthecode/BioinfoFlow/compare/0.1.0...0.2.0) (2026-07-28)


### Features

* adapt model invocation by provider profile ([2811acf](https://github.com/lewismessthecode/BioinfoFlow/commit/2811acf876a1324cafa6665136968eb73bedc747))
* add agent attachment client contracts ([7365770](https://github.com/lewismessthecode/BioinfoFlow/commit/7365770e9669f00b933562cfcc2ebfda4c74859e))
* add agent attachment composer UI ([5bca39d](https://github.com/lewismessthecode/BioinfoFlow/commit/5bca39d193a7dd6d141dc4c0d21fbcffd1560728))
* add agent custom instructions settings ([abb4ca1](https://github.com/lewismessthecode/BioinfoFlow/commit/abb4ca1f1de3fb320a5d4ddfcffaa8246ce05dac))
* add artifact file tree ([#204](https://github.com/lewismessthecode/BioinfoFlow/issues/204)) ([ac263da](https://github.com/lewismessthecode/BioinfoFlow/commit/ac263da46ffe4486ab803cc2c44fdc13d798ba64))
* add balanced agent context search ([daab875](https://github.com/lewismessthecode/BioinfoFlow/commit/daab875ecd6b4475659824875597830bbc9f1a66))
* add configurable voice dictation ([#177](https://github.com/lewismessthecode/BioinfoFlow/issues/177)) ([f9d612e](https://github.com/lewismessthecode/BioinfoFlow/commit/f9d612e024883e764ac12d26a3c5bdc7f79376cf))
* add immutable agent custom instructions ([b412dc5](https://github.com/lewismessthecode/BioinfoFlow/commit/b412dc5ef1a17bf2c03e5cb2ce270a7ef455165f))
* add multimodal model input parts ([1e5631c](https://github.com/lewismessthecode/BioinfoFlow/commit/1e5631c49526b5472afa0acf5918f1e4a8b8768d))
* add native ngs skill suite ([194bcab](https://github.com/lewismessthecode/BioinfoFlow/commit/194bcabce216822df724221133d45ab855aa27a5))
* add provider catalog profiles ([77dd593](https://github.com/lewismessthecode/BioinfoFlow/commit/77dd593d14f6716f9e4bf98841d498f0a3cd6ca6))
* add readable project directory names ([4e3900c](https://github.com/lewismessthecode/BioinfoFlow/commit/4e3900c34abb7e0050c93539e7f03bc23abd1eaa))
* add session attachment read tools ([a943b9d](https://github.com/lewismessthecode/BioinfoFlow/commit/a943b9dc225be443afc3f2e4c6733fa93909e8e3))
* add structured agent context mentions ([1510435](https://github.com/lewismessthecode/BioinfoFlow/commit/151043555996bc5fb4b2ed8788bc88af16c9b1a8))
* add subagent workspace ([98a81e0](https://github.com/lewismessthecode/BioinfoFlow/commit/98a81e083a4e3506bad3187cdcf826b4a6b0f9cf))
* allocate unique project directories ([24eeb44](https://github.com/lewismessthecode/BioinfoFlow/commit/24eeb4491238b136ebafc0e76ef87c535de49e67))
* allow agent bash to access Docker ([6d726f6](https://github.com/lewismessthecode/BioinfoFlow/commit/6d726f6e280f96daa435ecaa2dabae4ce17c4da9))
* bundle reviewed llm model catalog ([26ebda0](https://github.com/lewismessthecode/BioinfoFlow/commit/26ebda06f26258a057c12ffc0e272ac5b3752c6b))
* configure localhost API at runtime ([8155373](https://github.com/lewismessthecode/BioinfoFlow/commit/8155373df84fca44b8fcf317a7ff025f59631438))
* configure SSH jump hosts in connections UI ([0c254ba](https://github.com/lewismessthecode/BioinfoFlow/commit/0c254baa767bcc5563bd363d864fc1cb489444c5))
* coordinate child agent lifecycle ([297f39c](https://github.com/lewismessthecode/BioinfoFlow/commit/297f39c48f9ae9a241f84356c599ee63e6ca90d1))
* create projects in readable directories ([7ee0ef0](https://github.com/lewismessthecode/BioinfoFlow/commit/7ee0ef0ccd7fff93dabc72319bf343672b1f36ea))
* expose native skill resource directories ([e7c4765](https://github.com/lewismessthecode/BioinfoFlow/commit/e7c476577b4a5529ba9e254a71156018639f0596))
* ingest agent files folders and images ([53039fc](https://github.com/lewismessthecode/BioinfoFlow/commit/53039fcb0272fbf27ed79c8c64393c550914ad80))
* integrate agent context attachments ([401136d](https://github.com/lewismessthecode/BioinfoFlow/commit/401136d5cd7fa12dae90e3d1d7675ec01e8d1179))
* model SSH jump connections ([3e361bb](https://github.com/lewismessthecode/BioinfoFlow/commit/3e361bb9e426a08f41a10c3d8bf7bd1ef207773e))
* open terminals through SSH jump hosts ([42994cb](https://github.com/lewismessthecode/BioinfoFlow/commit/42994cbaecdbc04aa1fb6091ca5f272a8df1c731))
* persist agent collaboration tree ([0747e36](https://github.com/lewismessthecode/BioinfoFlow/commit/0747e368eeaf442e2be029a6f2ab8f572791f6e1))
* persist agent session attachments ([f932add](https://github.com/lewismessthecode/BioinfoFlow/commit/f932add11dc0d8fe3729b93af5a99ddbba36ffb9))
* persist managed project directory names ([db41b9f](https://github.com/lewismessthecode/BioinfoFlow/commit/db41b9f08079a1c9071bd4d2a6cc6ae20d98c99e))
* redesign landing page ([611c505](https://github.com/lewismessthecode/BioinfoFlow/commit/611c5055db7243992af71d3f540ac85e76985c50))
* refine agent workspace tabs ([23bc0fa](https://github.com/lewismessthecode/BioinfoFlow/commit/23bc0fa220e6e1d6e5f02b9904b54edfeadd20c8))
* report provider verification checkpoints ([7cb108d](https://github.com/lewismessthecode/BioinfoFlow/commit/7cb108d6ad22081ea72f9415ecffaecbb3b9d054))
* resolve child context and model fallback ([f5bedb0](https://github.com/lewismessthecode/BioinfoFlow/commit/f5bedb0656643fe3d6bdfbdeba70855095a0448f))
* resolve structured agent context references ([a964d4d](https://github.com/lewismessthecode/BioinfoFlow/commit/a964d4df90a4b5d66bffed31b57d705b497ba560))
* route SSH commands through jump hosts ([3f191ce](https://github.com/lewismessthecode/BioinfoFlow/commit/3f191ceab03dc0c1a6c9b4b0bf06860cffc47cb9))
* seed native skills from curl installer ([998dc44](https://github.com/lewismessthecode/BioinfoFlow/commit/998dc4468b586ea6dcb8e7d7f58c5eb0d830cd95))
* show child agent lifecycle ([135dc3f](https://github.com/lewismessthecode/BioinfoFlow/commit/135dc3fd78632569133f1d0f10c2afa23965c551))
* spawn and list child agents ([b7c1ee5](https://github.com/lewismessthecode/BioinfoFlow/commit/b7c1ee5228b07a46d8fc4376955a4f92724c1b59))
* strengthen the agent system prompt ([7810d3a](https://github.com/lewismessthecode/BioinfoFlow/commit/7810d3a8e44b3a1b37631a86cd2f16986f5b6afc))
* support configurable installer ports ([d185b13](https://github.com/lewismessthecode/BioinfoFlow/commit/d185b135878443ca60c1e25496b3f8cd2ef9a189))
* use Inter on landing page ([5a0b4af](https://github.com/lewismessthecode/BioinfoFlow/commit/5a0b4afb310f8196ff4cd64b41ca1b8dab1e00d6))


### Bug Fixes

* advertise only available agent skills ([0640307](https://github.com/lewismessthecode/BioinfoFlow/commit/06403077dba363e07d26f814ad7bf6713f8ea2df))
* align agent settings update contract ([1248f20](https://github.com/lewismessthecode/BioinfoFlow/commit/1248f20f19d24d0396e123c01c401c8d7ccc3ca2))
* align child model authority ([7416ed0](https://github.com/lewismessthecode/BioinfoFlow/commit/7416ed014fa35f54513c7a8fe9fc5ecc52ec9336))
* align scheduler activity with dashboard ([#176](https://github.com/lewismessthecode/BioinfoFlow/issues/176)) ([965edae](https://github.com/lewismessthecode/BioinfoFlow/commit/965edae5d5c44f66a2287b382326946afc285dbe))
* align shell effects with risk grammar ([9d5d29b](https://github.com/lewismessthecode/BioinfoFlow/commit/9d5d29b0d2bbdcbe06a99ec15ec82fbe71edff2c))
* allow exiting public demo ([29c1e56](https://github.com/lewismessthecode/BioinfoFlow/commit/29c1e5640ee33bcb47afaab9dbcd732b727d4960))
* apply agent mode with turn creation ([b43a9ba](https://github.com/lewismessthecode/BioinfoFlow/commit/b43a9ba646102423e7b9ebdfc16433724c61ff3e))
* auto-detect host GPUs in Docker deployments ([#175](https://github.com/lewismessthecode/BioinfoFlow/issues/175)) ([a76f932](https://github.com/lewismessthecode/BioinfoFlow/commit/a76f9325316b33e58534c27a8ae353a6d666814b))
* avoid reserved project directory names ([8453954](https://github.com/lewismessthecode/BioinfoFlow/commit/84539543a4f1cd3b8b46e91a25737289d3b56641))
* cache bubblewrap capability checks ([9bd66db](https://github.com/lewismessthecode/BioinfoFlow/commit/9bd66dbea5065d61054da14db119b04c367b4bde))
* clarify the agent product-source boundary ([a4ade47](https://github.com/lewismessthecode/BioinfoFlow/commit/a4ade4732c0bdb9f76cc167bb983c0361d41b88d))
* classify bare env as read only ([9f9787a](https://github.com/lewismessthecode/BioinfoFlow/commit/9f9787a66f900713f62cae1efcdc8d29b6f1def7))
* classify recovered batch tool failures ([0467d14](https://github.com/lewismessthecode/BioinfoFlow/commit/0467d144039541dbef3e61641af179e8089e9053))
* clean unopened project reservations ([bd286e2](https://github.com/lewismessthecode/BioinfoFlow/commit/bd286e2a2bc21dea43cc7a9bc800efb0b2c54741))
* close project reservation fds on cancellation ([daaa220](https://github.com/lewismessthecode/BioinfoFlow/commit/daaa2201d43e6e06248b911f96a54fd2c3f13b38))
* compile Kimi Code requests ([7ed5837](https://github.com/lewismessthecode/BioinfoFlow/commit/7ed5837f5c33b9dda95383a0484e7406bd7ba6a5))
* compile Responses reasoning options ([d7b4c30](https://github.com/lewismessthecode/BioinfoFlow/commit/d7b4c306a67091e1a99b51f52ac24a7e807a3316))
* constrain plan tools to registry ([d41cbe5](https://github.com/lewismessthecode/BioinfoFlow/commit/d41cbe58fc953483e62b26bf0a1e969ce8d5e20b))
* continue after exclusive batch cancellations ([d17f05c](https://github.com/lewismessthecode/BioinfoFlow/commit/d17f05cb197d9f8148be4b5e6f1cb7f112712d12))
* continue after recoverable tool failures ([dfc9d2a](https://github.com/lewismessthecode/BioinfoFlow/commit/dfc9d2a8d08e55a7dc9c247895e431882f12438a))
* correct workspace collapse icon ([#202](https://github.com/lewismessthecode/BioinfoFlow/issues/202)) ([e54dda7](https://github.com/lewismessthecode/BioinfoFlow/commit/e54dda784d084c5689aa10d33f4dff2a65e816ad))
* declare collaboration tool write scopes ([b5fd3ed](https://github.com/lewismessthecode/BioinfoFlow/commit/b5fd3ed7c4576cd2dbef59db16fada29de653971))
* derive safe plan mode tools ([6a3171d](https://github.com/lewismessthecode/BioinfoFlow/commit/6a3171dd64104d46c12f14b46e1e2e3766cd226d))
* diagnose Harbor image pull failures ([dd7b2d0](https://github.com/lewismessthecode/BioinfoFlow/commit/dd7b2d06b96ed2e367b9a2b17f20177bdedcfb6e))
* disable open mode menu during active turns ([304f3ae](https://github.com/lewismessthecode/BioinfoFlow/commit/304f3aeb896e16d21e192f3f6816faff47942c1a))
* distinguish root worker plan guidance ([54b149c](https://github.com/lewismessthecode/BioinfoFlow/commit/54b149c98c666f6b28a5438c1c5edfebde21f829))
* enforce approval barriers for parallel results ([f7b8ec4](https://github.com/lewismessthecode/BioinfoFlow/commit/f7b8ec4cf6e025d1ea0639dc7bc56218ff62e07c))
* enforce CI and release invariants ([d176af9](https://github.com/lewismessthecode/BioinfoFlow/commit/d176af913b5c3ca8c9e03ccb9ade4a1a9322b65f))
* enforce project environment defaults ([#197](https://github.com/lewismessthecode/BioinfoFlow/issues/197)) ([f594ab7](https://github.com/lewismessthecode/BioinfoFlow/commit/f594ab71c8d65fe4e427315df6aa70e0cb9054f0))
* enforce runtime skill exposure ([8a82493](https://github.com/lewismessthecode/BioinfoFlow/commit/8a8249354501591139bacd599843f736ca5110c1))
* expose platform lifecycle tools to agents ([64166e2](https://github.com/lewismessthecode/BioinfoFlow/commit/64166e266ce0f0a2779d67ea2f3a9a17f27093d1))
* expose workflow tool failure details ([f3d597b](https://github.com/lewismessthecode/BioinfoFlow/commit/f3d597ba1eba9f6832e5c3791deee399197f2d0b))
* fail closed on auth configuration ([0338406](https://github.com/lewismessthecode/BioinfoFlow/commit/03384069358f34566d35dd9ff5cbf42fc287a1c2))
* fence mode updates during active turns ([91a79b2](https://github.com/lewismessthecode/BioinfoFlow/commit/91a79b209e717269e269b831db3cdff694833cff))
* gate vercel analytics in self-hosted builds ([eb2f634](https://github.com/lewismessthecode/BioinfoFlow/commit/eb2f634a223a9075bbef9faafcf0f0a9a4f57e33))
* guard pending agent mode intent ([fe0f335](https://github.com/lewismessthecode/BioinfoFlow/commit/fe0f3351cfa1aa37a33d7717bc703f6504e7e8e5))
* harden agent attachment handling ([7a5aa6f](https://github.com/lewismessthecode/BioinfoFlow/commit/7a5aa6f49307fe59cea0b3e408b369af7a6065ef))
* harden agent collaboration persistence ([e3c805c](https://github.com/lewismessthecode/BioinfoFlow/commit/e3c805c363d3107389ab1111cf2ba2ef0b87b874))
* harden child agent spawning ([503de50](https://github.com/lewismessthecode/BioinfoFlow/commit/503de502e6b27c5f844d51da1f0afef9a7d4aaa7))
* harden child model preflight ([5836361](https://github.com/lewismessthecode/BioinfoFlow/commit/5836361d0cf47363bc740da3f53aedc0e28fd4a5))
* harden project directory reservations ([96d8801](https://github.com/lewismessthecode/BioinfoFlow/commit/96d880162e935ac81aaee29a7c384df9e860c89f))
* harden shell introspection proof ([77b3f26](https://github.com/lewismessthecode/BioinfoFlow/commit/77b3f263f033d5441b65ce7066affeb51d3034f3))
* harden SSH jump routing ([8af0250](https://github.com/lewismessthecode/BioinfoFlow/commit/8af0250e2d6533e6f41857085489fe3ddade963e))
* harden workflow image resolution ([0c508ad](https://github.com/lewismessthecode/BioinfoFlow/commit/0c508ad2bcfc60e8b2dc7f8760d59f4450c99192))
* inject stable agent date context ([#173](https://github.com/lewismessthecode/BioinfoFlow/issues/173)) ([2fd390e](https://github.com/lewismessthecode/BioinfoFlow/commit/2fd390e7ef40ac52df2f50cc7dc9a42543a29b32))
* invalidate dependent jump connections ([d1cb8e8](https://github.com/lewismessthecode/BioinfoFlow/commit/d1cb8e891baa1abb93198dd78bd8f9027c7bb6c2))
* isolate agent from product source ([#187](https://github.com/lewismessthecode/BioinfoFlow/issues/187)) ([a156b16](https://github.com/lewismessthecode/BioinfoFlow/commit/a156b16b1553fe18bf9379396bd60cc7ce6363ac))
* isolate child lifecycle observability ([e5f0ea2](https://github.com/lewismessthecode/BioinfoFlow/commit/e5f0ea2b8330628d0024771eeea93b73e92504d7))
* isolate collaboration notifications ([b6f2ce5](https://github.com/lewismessthecode/BioinfoFlow/commit/b6f2ce510916e5fbdd6c27dac117a14aa15f9f20))
* isolate subagent spawn transactions ([c487a67](https://github.com/lewismessthecode/BioinfoFlow/commit/c487a67db49056f60b3dd200d34637af305b904b))
* keep active agent conversations continuous ([#174](https://github.com/lewismessthecode/BioinfoFlow/issues/174)) ([8817614](https://github.com/lewismessthecode/BioinfoFlow/commit/8817614d35ab951bfb01a2a4acde7fc25a89065a))
* keep Docker socket outside file capabilities ([cfe6d6b](https://github.com/lewismessthecode/BioinfoFlow/commit/cfe6d6b5a4618eb48e2734d7294cec83d3ddd4e0))
* keep provider setup backend driven ([7c8f2d9](https://github.com/lewismessthecode/BioinfoFlow/commit/7c8f2d94df1284a40d4ceec5585f9f5ce4bb5b71))
* make agent response actions reliable ([#171](https://github.com/lewismessthecode/BioinfoFlow/issues/171)) ([13f0001](https://github.com/lewismessthecode/BioinfoFlow/commit/13f000183879e1a49b6a0631ccc4659451aaaf6b))
* make bubblewrap namespace setup usable ([2b1f1e3](https://github.com/lewismessthecode/BioinfoFlow/commit/2b1f1e3e965797b3f7fda6993a339d3cf5375011))
* make composer provider logos theme-aware ([#198](https://github.com/lewismessthecode/BioinfoFlow/issues/198)) ([55f161d](https://github.com/lewismessthecode/BioinfoFlow/commit/55f161d3702f661fcaff3c0441036d08a312c81f))
* make file patch batches atomic ([b032c58](https://github.com/lewismessthecode/BioinfoFlow/commit/b032c58207397693047ebc970ef8620e974ab48e))
* make full access bypass risk approvals ([8d57c34](https://github.com/lewismessthecode/BioinfoFlow/commit/8d57c3499dcb2d22b6bbb0d18e8c51b40bbe736b))
* make registry endpoint lookup deterministic ([bda9cb7](https://github.com/lewismessthecode/BioinfoFlow/commit/bda9cb7b89ef0d8dd029d4d63a2ac5220500cdd9))
* make turn mode claim atomic ([589adce](https://github.com/lewismessthecode/BioinfoFlow/commit/589adce54a2f2e3bc0ffa80464e27f9d1babb2cb))
* mark nonzero bash exits as failed ([6fe97c2](https://github.com/lewismessthecode/BioinfoFlow/commit/6fe97c2ed5abac38f6daa2e7561188a0383ba4f3))
* merge agent migration heads ([59fb3f3](https://github.com/lewismessthecode/BioinfoFlow/commit/59fb3f396926eada5c30cbf2bcc185ab614f4394))
* merge nested shell semantics ([a0f0411](https://github.com/lewismessthecode/BioinfoFlow/commit/a0f0411cc1532b2edf6169ff008a6e52f5de9c7d))
* mount executable root in bubblewrap probe ([c000c0a](https://github.com/lewismessthecode/BioinfoFlow/commit/c000c0aa908586399baf8db75b20b82d171b97e8))
* normalize provider reasoning controls ([450910a](https://github.com/lewismessthecode/BioinfoFlow/commit/450910a4c3dad05a115c61ca67116a8ff43abd62))
* order mode snapshot before optional arguments ([71d8151](https://github.com/lewismessthecode/BioinfoFlow/commit/71d81517d62caad766f38aa11c680947ee260171))
* package btop and refine scheduler UI ([#170](https://github.com/lewismessthecode/BioinfoFlow/issues/170)) ([c3925a6](https://github.com/lewismessthecode/BioinfoFlow/commit/c3925a60d0db076b380a7f6a569342191b7f3a62))
* preserve agent task state across compaction ([b7fde13](https://github.com/lewismessthecode/BioinfoFlow/commit/b7fde13366afe296ee8596842c83dcd596ab4393))
* preserve canonical multimodal input order ([81ddb54](https://github.com/lewismessthecode/BioinfoFlow/commit/81ddb544c48f33838e8392f5fae61423969c80cf))
* preserve child lifecycle ordering ([7caec8c](https://github.com/lewismessthecode/BioinfoFlow/commit/7caec8ce26ed6ddcc6bc08231140aa4c53da1f6f))
* preserve child plan prompt prefix ([c0f3d61](https://github.com/lewismessthecode/BioinfoFlow/commit/c0f3d612e49f659f549cc2332f859a17d3215d07))
* preserve child reasoning and attachment cleanup ([e123070](https://github.com/lewismessthecode/BioinfoFlow/commit/e12307005ca27cc1a4702be8a86a15b980b4b45b))
* preserve collaboration steers ([d0a9491](https://github.com/lewismessthecode/BioinfoFlow/commit/d0a9491c1c66b97e622471a9d8cad376f36b58f9))
* preserve file metadata during patch rollback ([6c28155](https://github.com/lewismessthecode/BioinfoFlow/commit/6c281558b74331e1499e4b57aa032410a1d66ab8))
* preserve installer data ownership ([#151](https://github.com/lewismessthecode/BioinfoFlow/issues/151)) ([d4dc54d](https://github.com/lewismessthecode/BioinfoFlow/commit/d4dc54d72cd43be61d99715156196372dd98fefd))
* preserve mode across queued turns ([cddd2f0](https://github.com/lewismessthecode/BioinfoFlow/commit/cddd2f0191e0a095f6de3f856aec4f3e6bb8de74))
* preserve ordered parallel tool execution ([6c0d6c3](https://github.com/lewismessthecode/BioinfoFlow/commit/6c0d6c3247b6863df30a46a3b22d369166e3403e))
* preserve plan batch atomicity ([1bc90a9](https://github.com/lewismessthecode/BioinfoFlow/commit/1bc90a94d99a85146504fe1a7ef68b795f378783))
* preserve private continuation metadata ([1731106](https://github.com/lewismessthecode/BioinfoFlow/commit/17311060a5ece2e52bb5f66db9309ad8a9505c77))
* preserve project directory transactions ([e32f549](https://github.com/lewismessthecode/BioinfoFlow/commit/e32f54996c045c295ca6b282b25efdd9df26b021))
* preserve release marker in dependency lock ([fb32431](https://github.com/lewismessthecode/BioinfoFlow/commit/fb3243133d5bb9496a44c0a2bc0e28e9eacde58d))
* preserve same-mode toolset policies ([0efca12](https://github.com/lewismessthecode/BioinfoFlow/commit/0efca1237b1305f66cb50667f07d06f57f63d1eb))
* preserve SSH connection route drafts ([42da87c](https://github.com/lewismessthecode/BioinfoFlow/commit/42da87c52d1ead92206c57ea7531084221dd7676))
* preserve stale tool batch accuracy ([65ae063](https://github.com/lewismessthecode/BioinfoFlow/commit/65ae063fe3534c78dc64c400362feea3d5f0ce61))
* preserve unopened project directories ([0abd959](https://github.com/lewismessthecode/BioinfoFlow/commit/0abd9598acb2c660a3e2a6a82ef0894ca61c19a5))
* protect legacy project directories ([6d3c8cc](https://github.com/lewismessthecode/BioinfoFlow/commit/6d3c8cc114add7e4da4058d88cb1f8479bf230fd))
* quarantine project directory cleanup ([dec1d10](https://github.com/lewismessthecode/BioinfoFlow/commit/dec1d103cf307cfe04428ae4c18c802db1d3a58b))
* quarantine unopened project cleanup ([fb0ab8f](https://github.com/lewismessthecode/BioinfoFlow/commit/fb0ab8fb8ad83e2dbc7de48ad114bbdb991a5ed2))
* reconcile legacy llm providers ([ccaec8a](https://github.com/lewismessthecode/BioinfoFlow/commit/ccaec8af24ad907e6fdb3b58cf9aa821d1a06530))
* recover child agent publications ([003b410](https://github.com/lewismessthecode/BioinfoFlow/commit/003b410ac26f58c826bf7183d6794c7f893b0c6f))
* recover incomplete installer releases ([#150](https://github.com/lewismessthecode/BioinfoFlow/issues/150)) ([443232b](https://github.com/lewismessthecode/BioinfoFlow/commit/443232b8cbaf395c6ad12c66b98e5a1986fd255a))
* recover queued child followups ([1ce435b](https://github.com/lewismessthecode/BioinfoFlow/commit/1ce435b332f8745791c18d760a72ae092f17ea12))
* recover stale offered tool calls ([076a701](https://github.com/lewismessthecode/BioinfoFlow/commit/076a701dbd617cd64679dffcac3921b7c4e1f2c4))
* refine SSH connection feedback ([413ebb1](https://github.com/lewismessthecode/BioinfoFlow/commit/413ebb17816fd7c43aea0f352b858b1d90db17b2))
* reject jump IDs on direct connections ([77a8a8f](https://github.com/lewismessthecode/BioinfoFlow/commit/77a8a8f7d613b93cf806aa07173564aceef37436))
* reject protected Docker socket locations ([f7e62ea](https://github.com/lewismessthecode/BioinfoFlow/commit/f7e62eaed7c4e3d5e5abd824ad9253a7d9313277))
* remove implicit prefetch registry fallback ([58baa7a](https://github.com/lewismessthecode/BioinfoFlow/commit/58baa7a8fc5cdfbb8646a05652b7f9b69a864663))
* remove local first-run configuration friction ([a43cde1](https://github.com/lewismessthecode/BioinfoFlow/commit/a43cde15479071aab257428f316cd07c6d26f1fb))
* report agent sandbox probe failures ([cb04e38](https://github.com/lewismessthecode/BioinfoFlow/commit/cb04e38f833b36ceed02142e562dd7753abc9e2c))
* report canonical execution tools ([37df995](https://github.com/lewismessthecode/BioinfoFlow/commit/37df9951be4b136294b6d159950f8858720f7ffc))
* reserve all legacy project identifiers ([6580e9b](https://github.com/lewismessthecode/BioinfoFlow/commit/6580e9bcacb61afabd04768dcd48ff42bda4a98a))
* resolve GitHub WDL sources ([1563661](https://github.com/lewismessthecode/BioinfoFlow/commit/15636616ec6e3ef624d0efda43c039046b98f74b))
* resolve workflow images from explicit registries ([b8dc1e2](https://github.com/lewismessthecode/BioinfoFlow/commit/b8dc1e275d2eebe67b9144dfc49d6cbd7c87699a))
* restore dark code block syntax colors ([#196](https://github.com/lewismessthecode/BioinfoFlow/issues/196)) ([b42b999](https://github.com/lewismessthecode/BioinfoFlow/commit/b42b999e52431951393dbeb50b6e44a50af6e308))
* restore network and voice deployment reliability ([b8b3cd6](https://github.com/lewismessthecode/BioinfoFlow/commit/b8b3cd66837825c79e0b4d74e42447fde767e634))
* restore release and migration compatibility ([3129a2a](https://github.com/lewismessthecode/BioinfoFlow/commit/3129a2a63e5867de40936161f8c102c8f3d3f2a6))
* resume approved plan actions safely ([c34d93f](https://github.com/lewismessthecode/BioinfoFlow/commit/c34d93f6c8cbcbbc5e6ac997ded4587fb700e285))
* retain agent mode until refresh confirms ([0e0e701](https://github.com/lewismessthecode/BioinfoFlow/commit/0e0e7014afb8e66766e846d2858bcab9e511725b))
* reuse the per-iteration skill registry ([b6e01fc](https://github.com/lewismessthecode/BioinfoFlow/commit/b6e01fc43146368fb555a2ebfa212beeb63a1b6c))
* rollback all file patch failures ([cfabc47](https://github.com/lewismessthecode/BioinfoFlow/commit/cfabc474655e18ea58ca6e1064ed60955330c612))
* sanitize child agent failure events ([9d584e7](https://github.com/lewismessthecode/BioinfoFlow/commit/9d584e7fd979edf3804426711f29ade8a558df4b))
* scope agent failure sanitization ([4d29bc7](https://github.com/lewismessthecode/BioinfoFlow/commit/4d29bc7cc3b9fab2f99d1c7efce8feedb95a28c2))
* scope retry progress to the active response ([99b494f](https://github.com/lewismessthecode/BioinfoFlow/commit/99b494fdbb4d373d4c64815340422e4915b436f5))
* send agent mode with each turn ([91bd0bc](https://github.com/lewismessthecode/BioinfoFlow/commit/91bd0bcdff66a0eb4ce1a59c9eba100c38dc1397))
* simplify appearance preview skeletons ([#203](https://github.com/lewismessthecode/BioinfoFlow/issues/203)) ([c8b62d4](https://github.com/lewismessthecode/BioinfoFlow/commit/c8b62d4295d12505b0b3db7127daed89ac37d224))
* speed up agent history and quiet GPU probes ([#181](https://github.com/lewismessthecode/BioinfoFlow/issues/181)) ([07333b4](https://github.com/lewismessthecode/BioinfoFlow/commit/07333b43811454f469b875f2db96933b0894f0cb))
* stabilize SSH route editing state ([f9dc331](https://github.com/lewismessthecode/BioinfoFlow/commit/f9dc331377d3abe1940e1c54a2e1796f1fa27930))
* stop composer placeholder animation after submit ([#169](https://github.com/lewismessthecode/BioinfoFlow/issues/169)) ([287bd50](https://github.com/lewismessthecode/BioinfoFlow/commit/287bd507528549454e92f21517a18dcef3b75b20))
* stop tool batches at approval barriers ([aa7ecc6](https://github.com/lewismessthecode/BioinfoFlow/commit/aa7ecc6970f0ae969cf31da8f49845eff0d4763e))
* strengthen custom instructions settings states ([abf2307](https://github.com/lewismessthecode/BioinfoFlow/commit/abf230756fd7919847a24720cc3febbdf37af87f))
* terminalize stale tool activity ([869ad26](https://github.com/lewismessthecode/BioinfoFlow/commit/869ad262850d95297b591a8c0f4d3ab26617ed40))
* tighten agent attachment types ([27a4078](https://github.com/lewismessthecode/BioinfoFlow/commit/27a4078901f52901166eaf34ce555f48d2bb0de3))
* tolerate invalid sandbox probe output ([6708acd](https://github.com/lewismessthecode/BioinfoFlow/commit/6708acd97f01b98f6b3f4ad8e1a20c3232fa5afa))
* tolerate partial databases in project migration ([a0fc085](https://github.com/lewismessthecode/BioinfoFlow/commit/a0fc08501b14894813f4a5e0dec66b689b833378))
* unify semantic highlight colors ([e334004](https://github.com/lewismessthecode/BioinfoFlow/commit/e3340043e033e5298f9c5e95358bcd59ee9c73dd))
* upload recovered release assets ([#153](https://github.com/lewismessthecode/BioinfoFlow/issues/153)) ([6bde920](https://github.com/lewismessthecode/BioinfoFlow/commit/6bde920a103949b7066c83d0aeaad38a513604d1))
* validate deterministic registry prefetch targets ([a5e273c](https://github.com/lewismessthecode/BioinfoFlow/commit/a5e273c56375f0840fecd6e6ef777746ab112805))
* verify Docker socket sandbox capability ([f192c8b](https://github.com/lewismessthecode/BioinfoFlow/commit/f192c8b8a292d7b34e09105e2991d48320606ca3))


### Performance Improvements

* stabilize agent mode prompt prefix ([adba912](https://github.com/lewismessthecode/BioinfoFlow/commit/adba91291dd847d738106ea9ec7951baed6bc877))

## [0.1.0] - 2026-07-21

This is the first formally tracked release of Bioinfoflow. Earlier development
history has been consolidated into this release instead of being listed pull
request by pull request.

### Highlights

- Added a local-first workspace for managing bioinformatics projects, files,
  workflow bindings, run history, and outputs.
- Added workflow registration and execution through shared Nextflow and
  WDL/MiniWDL adapters.
- Added persistent scheduling with concurrency controls, resource accounting,
  retries, timeouts, cleanup, and restart recovery.
- Added inspectable run DAGs, logs, events, inputs, audit trails, and collected
  results.
- Added an Agent that can inspect platform state, call tools, prepare work, and
  submit approved operations.
- Added explicit permission and approval boundaries for consequential Agent
  actions.
- Added managed local projects, existing-directory projects, and SSH-backed
  remote projects.
- Added saved remote connections, connection probes, remote terminals, and
  bounded remote Agent tools.
- Added configurable hosted and OpenAI-compatible model providers.
- Added the Next.js web interface for projects, workflows, runs, images,
  connections, scheduling, settings, terminals, and Agent sessions.
- Added the HTTP-only `bif` command-line client for automation and operational
  access.
- Added Docker Compose deployment, GHCR container publishing, CI, CodeQL, and
  pull request automation.

[0.1.0]: https://github.com/lewismessthecode/BioinfoFlow/releases/tag/0.1.0
