# FinSight 第三批100轮排查与修复记录

日期：2026-11-21（Asia/Shanghai）。基准：6ea343ed6e0f9be3d7cf2ed404d8a5470cdfac35；分支：main。

用户续授权第三批100轮，沿用证据驱动排查 → 失败复现 → 最小修复 → 实际验证，全部结束统一push一次。前两批记录：[第一批](AUDIT_100_ROUNDS_2026-11-18.md)、[第二批](AUDIT_100_ROUNDS_BATCH2_2026-11-18.md)。一轮为一个独立业务契约的实现、输入与断言核对；多个契约共享一次测试集合，不按工具调用、测试启动或参数个数计轮。

结果：4轮复现并修复，96轮在所列契约范围内未复现新缺陷。4个完整修复单元各一个commit，另用一个文档commit保存本台账；未重构、未新增依赖、未改前端。代码范围仅3个实现文件、3个回归文件。

## 架构与优先修复依据

Vue工作台 → FastAPI路由 → 服务/LangGraph → 外部工具与RAG → JSON/SQLite/可选PostgreSQL，入口和持久化边界见第一批。本批检查工具失败状态、模型输出、缓存时效、预算、组合计算，不改架构。

三类危险债务及证据：

- 工具真实协议与测试替身有差异：search不会总是抛异常，全部搜索失败实际返回`Search error:`文本。第二批仅验证异常路径，真实文本仍被纪要和公告计作成功（第1轮）。优先修这项：它直接把服务故障描述成没有资料。最小修改仅在两个现有消费者识别协议前缀，不改变通用搜索实现、不扩大到其他调用方。
- 上游失败数据跨层传播：东方财富外层、data和股票行的失败标记未检查，坏行会挤掉有效候选（第2轮）；坏diff结构又被成功空结果路径吞掉（第4轮）。最小修改加现有风格的状态判断，删除坏载荷返回空列表的两行；成功空diff=[]保留。
- 单位换算后缺数值校验：A股成交量乘100后可从有限值溢出Infinity，负成交量也会进入结果（第3轮）。最小修改过滤负量并复用safe_float校验乘积；正常0、A股手转股、港股不换算均有对照。

遵循KISS/YAGNI：只加消费者协议识别和数据边界判断，删除错误回退，无新依赖、无抽象重构。注释沿用所在文件的中文。

## 实际验证

- T：纪要、公告、真实search协议、LangChain包装与证据接线：77 passed、2 warnings、63.12秒。文件test_earnings_transcripts_tool、test_local_disclosure_date、test_search_provider_error_contract、test_langchain_tool_error_contract、test_live_tools_evidence，均位于backend/tests。新增回归实际调用search，在关闭全部源的作用域内复现错误文本，不依赖网络。
- S：东方财富3项修复后，63 passed、2.00秒，0 skip。文件test_cn_screener、test_cn_screener_filters、test_screener_fallback、test_screener_router、test_screener_tool，均位于backend/tests。中间两个修复阶段分别52/58 passed；最终S覆盖所有新增边界。
- C：最终代码树af28e39，17个完整测试文件（下列文件清单），404 passed、5 warnings、11.36秒，0 skip、0 error。覆盖所有100轮契约及4项修复全部24个新增参数展开用例。warning为极端数值回归故意触发的NumPy溢出和除零，相关断言通过。
- B：最终代码树af28e39的CI Stage2后端完整集合：8484 passed、2 skipped、13 warnings、436.89秒（7分16秒），0失败、0错误。Windows命令`.venv/Scripts/python.exe -m pytest -q backend/tests tests/rag_quality/test_rag_quality.py tests/regression/test_mock_tools_contract.py tests/unit/test_trace_emitter.py --tb=short -r s`；子进程RAG_EMBEDDING=hash。本批pytest进程串行运行，避免前批共享画像夹具的跨进程争用。
- 两项既有skip已核对源码：backend/tests/test_conversation_experience.py:14明确退役ConversationAgent；backend/tests/test_streaming.py:12需要运行后端服务器的手工集成。两者均不承担本批修复覆盖。13个warning为第三方弃用和极端数值回归触发的NumPy/Pandas溢出。
- 本地与远程CI分别报告；统一push和远程HEAD核验在台账提交后执行，最终消息报告本批SHA对应CI终态，不能用前两批结果替代。

C完整文件清单（均为backend/tests下的.py文件）：

test_budget_manager、test_cache、test_cn_screener、test_cn_screener_filters、test_earnings_transcripts_tool、test_financials_analyzer、test_langchain_tool_error_contract、test_local_disclosure_date、test_news_sentiment_batch、test_portfolio_optimizer、test_portfolio_stress、test_risk_attribution、test_screener_fallback、test_screener_router、test_screener_tool、test_search_provider_error_contract、test_smart_cache_market。

## 剩余风险与验证边界

- 本次识别已存在的`Search error:`前缀；其他形式的上游静默错误仍不由此保证。成功空文本仍表示无结果；单个源失败后仍有成功结果时保留有效资料。
- 东方财富坏载荷触发既有备用端点及fallback链；成功空列表仍可发布，后续页失败保留已有部分结果，这是现有行为。
- 测试用确定性数据和可恢复故障注入验证契约，不保证实时外部API可用性或在线LLM分析质量。预算与缓存检查限进程内语义；组合计算保留现有模型假设。
- 本地hash嵌入避免模型下载；远程检索门禁、浏览器E2E和Compose状态需实际核对。未复现仅限所列业务边界，不说明模块无其他问题。

## 逐轮证据

源码函数与测试函数经AST定位，并读取实现和关键回归输入/断言。参数展开只记一个业务契约。

| 轮次 | 检查目标 | 源码证据 | 测试证据 | 结论与验证 |
| --- | --- | --- | --- | --- |
| 1 | 搜索错误文本误计成功 | [backend/tools/earnings_transcripts.py:252](../../backend/tools/earnings_transcripts.py#L252) | [backend/tests/test_earnings_transcripts_tool.py:5](../../backend/tests/test_earnings_transcripts_tool.py#L5) | 旧代码2项失败、2项部分成功对照通过；纪要和公告同一协议修复；3ae3ae9；T通过 |
| 2 | 东方财富明确失败数据入选 | [backend/tools/cn_screener.py:58](../../backend/tools/cn_screener.py#L58) | [backend/tests/test_cn_screener.py:48](../../backend/tests/test_cn_screener.py#L48) | 旧代码9项失败；拒绝外层、data及行级失败标记；b8a220b；S通过 |
| 3 | 东方财富成交量负数与溢出 | [backend/tools/cn_screener.py:108](../../backend/tools/cn_screener.py#L108) | [backend/tests/test_cn_screener.py:61](../../backend/tests/test_cn_screener.py#L61) | 旧代码3项失败、3项合法对照通过；换算后再校验有限性、拒绝负数；82966da；S通过 |
| 4 | 东方财富坏载荷冒充空结果 | [backend/tools/cn_screener.py:58](../../backend/tools/cn_screener.py#L58) | [backend/tests/test_cn_screener.py:74](../../backend/tests/test_cn_screener.py#L74) | 旧代码4项失败、1项真实空结果对照通过；删除坏载荷返回空列表路径；af28e39；S通过 |
| 5 | 情绪模型股票身份 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:20](../../backend/tests/test_news_sentiment_batch.py#L20) | 未复现新缺陷；其他股票的分析标记不可用；C通过 |
| 6 | 情绪输入股票身份 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:28](../../backend/tests/test_news_sentiment_batch.py#L28) | 未复现新缺陷；分析前排除其他股票新闻；C通过 |
| 7 | 情绪模型文本证据 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:36](../../backend/tests/test_news_sentiment_batch.py#L36) | 未复现新缺陷；无文本新闻不占分析槽位；C通过 |
| 8 | 情绪上游失败 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:55](../../backend/tests/test_news_sentiment_batch.py#L55) | 未复现新缺陷；失败行不占用模型槽位；C通过 |
| 9 | 情绪中英标签 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:104](../../backend/tests/test_news_sentiment_batch.py#L104) | 未复现新缺陷；中英情绪标签保持一致；C通过 |
| 10 | 情绪模型部分失败 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:118](../../backend/tests/test_news_sentiment_batch.py#L118) | 未复现新缺陷；失败模型行不毁其他结果；C通过 |
| 11 | 情绪事件显示 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:140](../../backend/tests/test_news_sentiment_batch.py#L140) | 未复现新缺陷；事件文字和影响字段限制类型与长度；C通过 |
| 12 | 情绪旧结果失效 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:169](../../backend/tests/test_news_sentiment_batch.py#L169) | 未复现新缺陷；重分析失败不保留旧成功结论；C通过 |
| 13 | 情绪恢复状态 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:183](../../backend/tests/test_news_sentiment_batch.py#L183) | 未复现新缺陷；成功重分析去除旧不可用状态；C通过 |
| 14 | 情绪模型篡改 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:193](../../backend/tests/test_news_sentiment_batch.py#L193) | 未复现新缺陷；模型不能改原始新闻字段；C通过 |
| 15 | 情绪模型超额输出 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:202](../../backend/tests/test_news_sentiment_batch.py#L202) | 未复现新缺陷；未送模型新闻不获得模型结论；C通过 |
| 16 | 情绪尾部统计 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:214](../../backend/tests/test_news_sentiment_batch.py#L214) | 未复现新缺陷；未分析尾部不伪造置信度和中性计数；C通过 |
| 17 | 情绪置信度边界 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:226](../../backend/tests/test_news_sentiment_batch.py#L226) | 未复现新缺陷；非法置信度不污染有效标签；C通过 |
| 18 | 情绪数组坏项 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:260](../../backend/tests/test_news_sentiment_batch.py#L260) | 未复现新缺陷；坏条目按项降级；C通过 |
| 19 | 情绪返回容器 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:287](../../backend/tests/test_news_sentiment_batch.py#L287) | 未复现新缺陷；非数组JSON返回不可用分析；C通过 |
| 20 | 情绪空项标量 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:297](../../backend/tests/test_news_sentiment_batch.py#L297) | 未复现新缺陷；空项和标量不拖垮有效分析；C通过 |
| 21 | 情绪模型异常 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:319](../../backend/tests/test_news_sentiment_batch.py#L319) | 未复现新缺陷；模型调用失败显式抛错；C通过 |
| 22 | 情绪非JSON响应 | [backend/services/news_sentiment.py:52](../../backend/services/news_sentiment.py#L52) | [backend/tests/test_news_sentiment_batch.py:327](../../backend/tests/test_news_sentiment_batch.py#L327) | 未复现新缺陷；非JSON响应显式不可用；C通过 |
| 23 | 情绪统计失败标记 | [backend/services/news_sentiment.py:175](../../backend/services/news_sentiment.py#L175) | [backend/tests/test_news_sentiment_batch.py:156](../../backend/tests/test_news_sentiment_batch.py#L156) | 未复现新缺陷；汇总排除失败存量结论；C通过 |
| 24 | 情绪统计权重 | [backend/services/news_sentiment.py:175](../../backend/services/news_sentiment.py#L175) | [backend/tests/test_news_sentiment_batch.py:235](../../backend/tests/test_news_sentiment_batch.py#L235) | 未复现新缺陷；大小写与空格不改变权重；C通过 |
| 25 | 情绪统计标签 | [backend/services/news_sentiment.py:175](../../backend/services/news_sentiment.py#L175) | [backend/tests/test_news_sentiment_batch.py:247](../../backend/tests/test_news_sentiment_batch.py#L247) | 未复现新缺陷；只统计有效规范化标签；C通过 |
| 26 | 财报公司名称 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:14](../../backend/tests/test_financials_analyzer.py#L14) | 未复现新缺陷；坏公司名回退请求身份；C通过 |
| 27 | 财报模型身份 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:22](../../backend/tests/test_financials_analyzer.py#L22) | 未复现新缺陷；模型其他股票不能重标为请求股票；C通过 |
| 28 | 财报公司身份 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:29](../../backend/tests/test_financials_analyzer.py#L29) | 未复现新缺陷；公司身份不符不调用模型；C通过 |
| 29 | 财报可选资料 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:37](../../backend/tests/test_financials_analyzer.py#L37) | 未复现新缺陷；坏可选资料不拖垮有效分析；C通过 |
| 30 | 财报输入身份 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:45](../../backend/tests/test_financials_analyzer.py#L45) | 未复现新缺陷；其他股票财报不送模型；C通过 |
| 31 | 财报模型失败 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:66](../../backend/tests/test_financials_analyzer.py#L66) | 未复现新缺陷；失败模型结果不能变成功；C通过 |
| 32 | 财报上游状态 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:76](../../backend/tests/test_financials_analyzer.py#L76) | 未复现新缺陷；失败财报不送模型；C通过 |
| 33 | 财报章节形状 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:87](../../backend/tests/test_financials_analyzer.py#L87) | 未复现新缺陷；坏章节不保留非法结构；C通过 |
| 34 | 财报章节保留 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:97](../../backend/tests/test_financials_analyzer.py#L97) | 未复现新缺陷；有效章节内容保留；C通过 |
| 35 | 财报列表限额 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:118](../../backend/tests/test_financials_analyzer.py#L118) | 未复现新缺陷；分析列表仅含有效文本且限额；C通过 |
| 36 | 财报评级显示 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:133](../../backend/tests/test_financials_analyzer.py#L133) | 未复现新缺陷；坏标签不伪造评级；C通过 |
| 37 | 财报非JSON数值 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:143](../../backend/tests/test_financials_analyzer.py#L143) | 未复现新缺陷；坏JSON数据不送模型；C通过 |
| 38 | 财报失败载荷 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:155](../../backend/tests/test_financials_analyzer.py#L155) | 未复现新缺陷；失败包中的残留数值不作分析；C通过 |
| 39 | 财报分数边界 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:165](../../backend/tests/test_financials_analyzer.py#L165) | 未复现新缺陷；评级必须有效且在1至10；C通过 |
| 40 | 财报分数规范 | [backend/services/financials_analyzer.py:63](../../backend/services/financials_analyzer.py#L63) | [backend/tests/test_financials_analyzer.py:175](../../backend/tests/test_financials_analyzer.py#L175) | 未复现新缺陷；合法文本分数规范成数值；C通过 |
| 41 | 缓存休市识别 | [backend/services/smart_cache.py:109](../../backend/services/smart_cache.py#L109) | [backend/tests/test_smart_cache_market.py:10](../../backend/tests/test_smart_cache_market.py#L10) | 未复现新缺陷；周末与大陆节假日不标交易中；C通过 |
| 42 | 缓存收盘边界 | [backend/services/smart_cache.py:109](../../backend/services/smart_cache.py#L109) | [backend/tests/test_smart_cache_market.py:19](../../backend/tests/test_smart_cache_market.py#L19) | 未复现新缺陷；收盘和午休边界不标交易中；C通过 |
| 43 | 缓存美股夏令时 | [backend/services/smart_cache.py:43](../../backend/services/smart_cache.py#L43) | [backend/tests/test_smart_cache_market.py:42](../../backend/tests/test_smart_cache_market.py#L42) | 未复现新缺陷；纽约时区调整交易缓存；C通过 |
| 44 | 缓存开盘截断 | [backend/services/smart_cache.py:90](../../backend/services/smart_cache.py#L90) | [backend/tests/test_smart_cache_market.py:65](../../backend/tests/test_smart_cache_market.py#L65) | 未复现新缺陷；休市缓存不延续到下次开盘；C通过 |
| 45 | 缓存加密资产 | [backend/services/smart_cache.py:212](../../backend/services/smart_cache.py#L212) | [backend/tests/test_smart_cache_market.py:80](../../backend/tests/test_smart_cache_market.py#L80) | 未复现新缺陷；股票周末不延长加密资产缓存；C通过 |
| 46 | 工具预算上限 | [backend/orchestration/budget.py:66](../../backend/orchestration/budget.py#L66) | [backend/tests/test_budget_manager.py:8](../../backend/tests/test_budget_manager.py#L8) | 未复现新缺陷；超出工具次数预算抛错；C通过 |
| 47 | 轮次预算上限 | [backend/orchestration/budget.py:73](../../backend/orchestration/budget.py#L73) | [backend/tests/test_budget_manager.py:15](../../backend/tests/test_budget_manager.py#L15) | 未复现新缺陷；超出轮次预算抛错；C通过 |
| 48 | 工具预算包装 | [backend/orchestration/budget.py:97](../../backend/orchestration/budget.py#L97) | [backend/tests/test_budget_manager.py:22](../../backend/tests/test_budget_manager.py#L22) | 未复现新缺陷；实际调用计数并保留结果；C通过 |
| 49 | 工具预算缺失工具 | [backend/orchestration/budget.py:97](../../backend/orchestration/budget.py#L97) | [backend/tests/test_budget_manager.py:31](../../backend/tests/test_budget_manager.py#L31) | 未复现新缺陷；缺失属性错误包含工具名；C通过 |
| 50 | 预算非有限时间 | [backend/orchestration/budget.py:45](../../backend/orchestration/budget.py#L45) | [backend/tests/test_budget_manager.py:40](../../backend/tests/test_budget_manager.py#L40) | 未复现新缺陷；非有限时间配置回退有效值；C通过 |
| 51 | 缓存抖动边界 | [backend/orchestration/cache.py:56](../../backend/orchestration/cache.py#L56) | [backend/tests/test_cache.py:21](../../backend/tests/test_cache.py#L21) | 未复现新缺陷；非法抖动配置回退有效值；C通过 |
| 52 | 缓存布尔TTL | [backend/orchestration/cache.py:104](../../backend/orchestration/cache.py#L104) | [backend/tests/test_cache.py:32](../../backend/tests/test_cache.py#L32) | 未复现新缺陷；布尔TTL拒绝；C通过 |
| 53 | 缓存时钟跳变 | [backend/orchestration/cache.py:29](../../backend/orchestration/cache.py#L29) | [backend/tests/test_cache.py:40](../../backend/tests/test_cache.py#L40) | 未复现新缺陷；TTL依据单调钟；C通过 |
| 54 | 缓存淘汰时间 | [backend/orchestration/cache.py:144](../../backend/orchestration/cache.py#L144) | [backend/tests/test_cache.py:63](../../backend/tests/test_cache.py#L63) | 未复现新缺陷；墙钟后跳不改变淘汰顺序；C通过 |
| 55 | 缓存过期边界 | [backend/orchestration/cache.py:29](../../backend/orchestration/cache.py#L29) | [backend/tests/test_cache.py:89](../../backend/tests/test_cache.py#L89) | 未复现新缺陷；到期瞬间失效；C通过 |
| 56 | 缓存线程并发 | [backend/orchestration/cache.py:104](../../backend/orchestration/cache.py#L104) | [backend/tests/test_cache.py:264](../../backend/tests/test_cache.py#L264) | 未复现新缺陷；并发读写不抛异常；C通过 |
| 57 | 缓存容量护栏 | [backend/orchestration/cache.py:144](../../backend/orchestration/cache.py#L144) | [backend/tests/test_cache.py:306](../../backend/tests/test_cache.py#L306) | 未复现新缺陷；持续写入保持容量有界；C通过 |
| 58 | 缓存嵌套复制 | [backend/orchestration/cache.py:74](../../backend/orchestration/cache.py#L74) | [backend/tests/test_cache.py:332](../../backend/tests/test_cache.py#L332) | 未复现新缺陷；输入和返回对象不污染缓存；C通过 |
| 59 | 编排缓存隔离 | [backend/orchestration/cache.py:74](../../backend/orchestration/cache.py#L74) | [backend/tests/test_cache.py:344](../../backend/tests/test_cache.py#L344) | 未复现新缺陷；编排返回引用不污染缓存报价；C通过 |
| 60 | 归因零基准 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:12](../../backend/tests/test_risk_attribution.py#L12) | 未复现新缺陷；零方差基准不标实测beta；C通过 |
| 61 | 归因失败持仓 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:22](../../backend/tests/test_risk_attribution.py#L22) | 未复现新缺陷；失败持仓不污染权重；C通过 |
| 62 | 归因空持仓 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:58](../../backend/tests/test_risk_attribution.py#L58) | 未复现新缺陷；无数据不伪造测得零风险；C通过 |
| 63 | 归因行业规范 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:67](../../backend/tests/test_risk_attribution.py#L67) | 未复现新缺陷；空格不拆分相同行业；C通过 |
| 64 | 归因代码规范 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:78](../../backend/tests/test_risk_attribution.py#L78) | 未复现新缺陷；输出规范化股票代码；C通过 |
| 65 | 归因坏持仓 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:87](../../backend/tests/test_risk_attribution.py#L87) | 未复现新缺陷；坏条目不吞有效持仓；C通过 |
| 66 | 归因权重溢出 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:265](../../backend/tests/test_risk_attribution.py#L265) | 未复现新缺陷；巨大有限市值保持规范权重；C通过 |
| 67 | 归因坏市值 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:278](../../backend/tests/test_risk_attribution.py#L278) | 未复现新缺陷；非法市值不污染归因；C通过 |
| 68 | 归因缺行情 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:335](../../backend/tests/test_risk_attribution.py#L335) | 未复现新缺陷；缺行情不伪造风险对半分解；C通过 |
| 69 | 归因存储行接线 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:412](../../backend/tests/test_risk_attribution.py#L412) | 未复现新缺陷；shares与avg_cost可导出权重；C通过 |
| 70 | 归因市值优先 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:430](../../backend/tests/test_risk_attribution.py#L430) | 未复现新缺陷；显式市值不被成本推算覆盖；C通过 |
| 71 | 归因重复行 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:444](../../backend/tests/test_risk_attribution.py#L444) | 未复现新缺陷；重复明细使用各自行业；C通过 |
| 72 | 归因个股缺失 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:481](../../backend/tests/test_risk_attribution.py#L481) | 未复现新缺陷；beta回退明确标记；C通过 |
| 73 | 归因正常恢复 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:507](../../backend/tests/test_risk_attribution.py#L507) | 未复现新缺陷；实测beta清除降级标记；C通过 |
| 74 | 归因零权重 | [backend/services/risk_attribution.py:104](../../backend/services/risk_attribution.py#L104) | [backend/tests/test_risk_attribution.py:524](../../backend/tests/test_risk_attribution.py#L524) | 未复现新缺陷；零权重不影响覆盖率；C通过 |
| 75 | 归因日线身份 | [backend/services/risk_attribution.py:41](../../backend/services/risk_attribution.py#L41) | [backend/tests/test_risk_attribution.py:33](../../backend/tests/test_risk_attribution.py#L33) | 未复现新缺陷；其他股票日线排除；C通过 |
| 76 | 归因日线失败 | [backend/services/risk_attribution.py:41](../../backend/services/risk_attribution.py#L41) | [backend/tests/test_risk_attribution.py:42](../../backend/tests/test_risk_attribution.py#L42) | 未复现新缺陷；失败日线不作收益证据；C通过 |
| 77 | 归因历史状态 | [backend/services/risk_attribution.py:41](../../backend/services/risk_attribution.py#L41) | [backend/tests/test_risk_attribution.py:50](../../backend/tests/test_risk_attribution.py#L50) | 未复现新缺陷；不可用历史不作收益证据；C通过 |
| 78 | 归因收盘有限性 | [backend/services/risk_attribution.py:41](../../backend/services/risk_attribution.py#L41) | [backend/tests/test_risk_attribution.py:127](../../backend/tests/test_risk_attribution.py#L127) | 未复现新缺陷；非有限收盘排除；C通过 |
| 79 | 归因行情缺口 | [backend/services/risk_attribution.py:41](../../backend/services/risk_attribution.py#L41) | [backend/tests/test_risk_attribution.py:146](../../backend/tests/test_risk_attribution.py#L146) | 未复现新缺陷；缺口不导出跨缺口收益；C通过 |
| 80 | 归因代码长度 | [backend/services/risk_attribution.py:41](../../backend/services/risk_attribution.py#L41) | [backend/tests/test_risk_attribution.py:159](../../backend/tests/test_risk_attribution.py#L159) | 未复现新缺陷；超长代码不触发上游；C通过 |
| 81 | 归因失败历史包 | [backend/services/risk_attribution.py:41](../../backend/services/risk_attribution.py#L41) | [backend/tests/test_risk_attribution.py:169](../../backend/tests/test_risk_attribution.py#L169) | 未复现新缺陷；失败历史包不提供收益；C通过 |
| 82 | 归因历史包身份 | [backend/services/risk_attribution.py:41](../../backend/services/risk_attribution.py#L41) | [backend/tests/test_risk_attribution.py:178](../../backend/tests/test_risk_attribution.py#L178) | 未复现新缺陷；历史包身份必须匹配；C通过 |
| 83 | 归因收益溢出 | [backend/services/risk_attribution.py:41](../../backend/services/risk_attribution.py#L41) | [backend/tests/test_risk_attribution.py:188](../../backend/tests/test_risk_attribution.py#L188) | 未复现新缺陷；派生非有限收益排除；C通过 |
| 84 | 归因OLS单倍 | [backend/services/risk_attribution.py:86](../../backend/services/risk_attribution.py#L86) | [backend/tests/test_risk_attribution.py:98](../../backend/tests/test_risk_attribution.py#L98) | 未复现新缺陷；完全相关beta接近1；C通过 |
| 85 | 归因OLS双倍 | [backend/services/risk_attribution.py:86](../../backend/services/risk_attribution.py#L86) | [backend/tests/test_risk_attribution.py:116](../../backend/tests/test_risk_attribution.py#L116) | 未复现新缺陷；双倍收益beta接近2；C通过 |
| 86 | 归因OLS极值 | [backend/services/risk_attribution.py:86](../../backend/services/risk_attribution.py#L86) | [backend/tests/test_risk_attribution.py:206](../../backend/tests/test_risk_attribution.py#L206) | 未复现新缺陷；非有限方差不泄露NaN；C通过 |
| 87 | 优化布尔收益 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:113](../../backend/tests/test_portfolio_optimizer.py#L113) | 未复现新缺陷；布尔值不冒充100%收益；C通过 |
| 88 | 优化夏普溢出 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:118](../../backend/tests/test_portfolio_optimizer.py#L118) | 未复现新缺陷；派生夏普非有限则拒绝；C通过 |
| 89 | 优化股票身份 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:124](../../backend/tests/test_portfolio_optimizer.py#L124) | 未复现新缺陷；重复与空代码拒绝；C通过 |
| 90 | 优化代码规范 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:129](../../backend/tests/test_portfolio_optimizer.py#L129) | 未复现新缺陷；权重键使用规范代码；C通过 |
| 91 | 优化模拟次数 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:136](../../backend/tests/test_portfolio_optimizer.py#L136) | 未复现新缺陷；次数须正整数；C通过 |
| 92 | 优化矩阵形状 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:145](../../backend/tests/test_portfolio_optimizer.py#L145) | 未复现新缺陷；坏矩阵产生验证错误；C通过 |
| 93 | 优化无风险利率 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:152](../../backend/tests/test_portfolio_optimizer.py#L152) | 未复现新缺陷；非法利率拒绝；C通过 |
| 94 | 优化统计溢出 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:159](../../backend/tests/test_portfolio_optimizer.py#L159) | 未复现新缺陷；统计溢出在JSON返回前拒绝；C通过 |
| 95 | 优化前沿限额 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:166](../../backend/tests/test_portfolio_optimizer.py#L166) | 未复现新缺陷；非整倍采样仍守300点限额；C通过 |
| 96 | 优化近奇异协方差 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:327](../../backend/tests/test_portfolio_optimizer.py#L327) | 未复现新缺陷；浮点负方差噪声不泄露NaN；C通过 |
| 97 | 优化正常输出 | [backend/services/portfolio_optimizer.py:33](../../backend/services/portfolio_optimizer.py#L33) | [backend/tests/test_portfolio_optimizer.py:195](../../backend/tests/test_portfolio_optimizer.py#L195) | 未复现新缺陷；正常输入完整结果可严格JSON；C通过 |
| 98 | 压力测试证据 | [backend/tools/price_portfolio.py:218](../../backend/tools/price_portfolio.py#L218) | [backend/tests/test_portfolio_stress.py:21](../../backend/tests/test_portfolio_stress.py#L21) | 未复现新缺陷；缺有效因子贡献不伪造场景；C通过 |
| 99 | 压力测试部分失效 | [backend/tools/price_portfolio.py:218](../../backend/tools/price_portfolio.py#L218) | [backend/tests/test_portfolio_stress.py:31](../../backend/tests/test_portfolio_stress.py#L31) | 未复现新缺陷；坏场景不吞有效场景；C通过 |
| 100 | 压力测试溢出 | [backend/tools/price_portfolio.py:218](../../backend/tools/price_portfolio.py#L218) | [backend/tests/test_portfolio_stress.py:48](../../backend/tests/test_portfolio_stress.py#L48) | 未复现新缺陷；溢出场景不污染有效预测；C通过 |
