# FinSight 第二批100轮排查与修复记录

日期：2026-11-18。基准：69865d7138147378a0cd86b37c4ecc63c96c0465；分支：main。

这是用户续授权的第二批，与[第一批记录](AUDIT_100_ROUNDS_2026-11-18.md)分开计数。一轮指一个独立业务契约的源码检查、失败边界与测试断言核对；多个契约共享测试集合。100轮不等于100个缺陷、100次测试启动或100个提交。

结果：4轮复现并最小修复，96轮在所列契约内未复现新缺陷。修改4个实现文件、4个回归文件与本台账；未重构、未新增依赖、未修改前端或无关文件。4个完整修复分别提交，全部检查结束统一push一次。

## 最小方案与风险选择

架构仍是Vue工作台 → FastAPI → 业务服务/LangGraph → 工具与RAG → JSON/SQLite/可选PostgreSQL；本批聚焦工具到工作台及报告的数据边界，架构入口证据见第一批。

本批三类高风险技术债：

- 失败语义漂移：纪要与本地公告所有search调用抛异常时仍返回error=None，会把服务故障描述成没有资料（第2、3轮）。优先选这类：用户会据此判断信息是否存在。最小方案仅计数成功调用，全部异常返回search_failed，不更改通用搜索协议。
- 上游失败数据进入业务结果：Nasdaq明确失败行仍参与选股排序，挤掉真实候选（第4轮）。最小方案在现有行转换入口拒绝error、success=False、失败status。
- 日期只有格式、缺日历语义：新闻YYYY-MM-DD正则接受2026-02-30等日期，污染时效证据（第1轮）。最小方案复用现有datetime做日历验证，保留合法日期、ISO日期截断和空格处理。

四项都先运行旧代码新增回归得到失败，再修改实现；新增16个参数展开用例，包括成功空结果、部分成功、合法日期与失败行排序对照。遵循KISS/YAGNI：只增加必要边界判断及成功计数，不引入抽象或依赖。

## 实际验证

- N：新闻/纪要受影响集合95 passed、5 warnings、22.04秒：test_news_parsing、test_news_url_date、test_search_provider_error_contract、test_news_tool_error_contract、test_earnings_transcripts_tool、test_live_tools_evidence、test_langchain_tool_error_contract、test_www_prefix_strip，均位于backend/tests。
- S：公告/选股受影响集合89 passed、3.61秒：test_local_disclosure_date、test_us_screener、test_us_screener_filters、test_screener_fallback、test_screener_router、test_screener_tool、test_langchain_tool_error_contract、test_www_prefix_strip，均位于backend/tests。一次误指定不存在的test_screener.py，未收集测试；纠正路径后执行此集合通过。
- C：96个检查契约对应14个完整测试文件，最终树dca5919串行运行450 passed、6.90秒、0 skip、0 error：test_tencent_provider、test_baostock_provider、test_us_market、test_sec_companyfacts_quarterly、test_sec_tools、test_financial_tool_fallback、test_eps_revision_signal、test_cn_hk_period_sort、test_fundamental_metric_row_match、test_dashboard_data_fetcher_boundaries、test_dashboard_equity_boundaries、test_dashboard_news_ranking、test_quality_engine、test_report_validator，均位于backend/tests。
- B：CI Stage2后端完整集合本地8452 passed、2 skipped、13 warnings、2个setup error，701.34秒。启动树e24e2f1，运行期间补第3、4项修复，不能视为最终树完整重跑。两个error均为共享画像文件的WinError 5：test_langchain_tool_error_contract::test_cn_market_northbound_tool_error_is_redacted与test_langgraph_skeleton::test_resolve_subject_query_ticker_overrides_active_symbol；下方F串行重跑相关完整模块及4项修复集合。
- F：最终树dca5919串行运行4项修复的受影响集合及上述2个报错所在完整模块：152 passed、5 warnings、25.80秒，0 skip、0 error。集合为N与S并集，加test_langgraph_skeleton；此前4个跨进程setup错误均已在C/F执行，无需改产品代码。
- 并发诊断：先前B运行期间另启C，共享backend/tests/conftest.py中的data/memory/test_api_user*夹具文件；C出现448 passed、2个setup PermissionError。夹具使用进程内模块锁，不能隔离两个pytest进程。C及F改为串行验证；不以修改产品代码、跳过测试或放宽断言规避。
- B中2个既有skip已核对：backend/tests/test_conversation_experience.py:14退役ConversationAgent；backend/tests/test_streaming.py:12需要运行后端服务器的手工集成。它们不承担本次修复覆盖。13个warning主要是第三方弃用及极端数值回归故意触发的NumPy/Pandas溢出。
- 本地命令：Windows .venv/Scripts/python.exe -m pytest -q；B路径为backend/tests、tests/rag_quality/test_rag_quality.py、tests/regression/test_mock_tools_contract.py、tests/unit/test_trace_emitter.py，参数--tb=short -r s，子进程RAG_EMBEDDING=hash。
- 本地结果不代表远程CI；推送后另核对本批SHA对应流水线终态。

## 边界与剩余风险

- 成功搜索计数只能识别search抛出的异常；通用search若内部吞错并返回正常文本，本次不改变其协议，因此未覆盖这种上游静默降级。
- 用例以故障注入和确定性数据验证边界，未将真实外部API可用性或在线模型能力算作通过。
- 本地hash嵌入用于避免模型下载；检索服务与前端未改动。远程Ubuntu流程另验证整棵最终树与集成阶段。
- 无发现仅限所列契约，不能推论整个模块无债务；不以次数制造修复。

## 逐轮证据

源码与测试函数均经AST定位与人工核对实现、输入及断言；一轮多参数只记一个业务契约。

| 轮次 | 检查目标 | 源码证据 | 测试证据 | 结论与验证 |
| --- | --- | --- | --- | --- |
| 1 | 新闻不可能日期 | [backend/tools/utils.py:5](../../backend/tools/utils.py#L5) | [backend/tests/test_news_parsing.py:21](../../backend/tests/test_news_parsing.py#L21) | 旧代码4项失败；最小日历验证；N通过；c711a62 |
| 2 | 纪要全部搜索异常 | [backend/tools/earnings_transcripts.py:252](../../backend/tools/earnings_transcripts.py#L252) | [backend/tests/test_earnings_transcripts_tool.py:5](../../backend/tests/test_earnings_transcripts_tool.py#L5) | 旧代码1项失败；计数成功搜索、全部异常返回search_failed；N通过；e24e2f1 |
| 3 | 公告全部搜索异常 | [backend/tools/local_disclosure.py:170](../../backend/tools/local_disclosure.py#L170) | [backend/tests/test_local_disclosure_date.py:10](../../backend/tests/test_local_disclosure_date.py#L10) | 旧代码1项失败；成功空结果与部分失败保持原语义；S通过；eb6b993 |
| 4 | Nasdaq选股失败行 | [backend/tools/us_screener.py:33](../../backend/tools/us_screener.py#L33) | [backend/tests/test_us_screener.py:9](../../backend/tests/test_us_screener.py#L9) | 旧代码3项失败；拒绝明确失败候选；S通过；dca5919 |
| 5 | 腾讯报价内部代码 | [backend/tools/tencent_provider.py:38](../../backend/tools/tencent_provider.py#L38) | [backend/tests/test_tencent_provider.py:314](../../backend/tests/test_tencent_provider.py#L314) | 未复现新缺陷；内部股票代码须匹配请求；C通过 |
| 6 | 腾讯响应标签 | [backend/tools/tencent_provider.py:38](../../backend/tools/tencent_provider.py#L38) | [backend/tests/test_tencent_provider.py:321](../../backend/tests/test_tencent_provider.py#L321) | 未复现新缺陷；响应v_标签不能指向其他股票；C通过 |
| 7 | 腾讯现价昨收 | [backend/tools/tencent_provider.py:38](../../backend/tools/tencent_provider.py#L38) | [backend/tests/test_tencent_provider.py:307](../../backend/tests/test_tencent_provider.py#L307) | 未复现新缺陷；非正价格拒绝；C通过 |
| 8 | 腾讯涨跌幅溢出 | [backend/tools/tencent_provider.py:38](../../backend/tools/tencent_provider.py#L38) | [backend/tests/test_tencent_provider.py:296](../../backend/tests/test_tencent_provider.py#L296) | 未复现新缺陷；计算溢出不写Infinity；C通过 |
| 9 | 腾讯手转股 | [backend/tools/tencent_provider.py:38](../../backend/tools/tencent_provider.py#L38) | [backend/tests/test_tencent_provider.py:288](../../backend/tests/test_tencent_provider.py#L288) | 未复现新缺陷；转换成交量有限且非负；C通过 |
| 10 | 腾讯观测时间 | [backend/tools/tencent_provider.py:38](../../backend/tools/tencent_provider.py#L38) | [backend/tests/test_tencent_provider.py:256](../../backend/tests/test_tencent_provider.py#L256) | 未复现新缺陷；支持14位真实时间戳；C通过 |
| 11 | 腾讯缺失观测时间 | [backend/tools/tencent_provider.py:38](../../backend/tools/tencent_provider.py#L38) | [backend/tests/test_tencent_provider.py:264](../../backend/tests/test_tencent_provider.py#L264) | 未复现新缺陷；缺时间不伪造当前时刻；C通过 |
| 12 | 腾讯流通市值 | [backend/tools/tencent_provider.py:38](../../backend/tools/tencent_provider.py#L38) | [backend/tests/test_tencent_provider.py:270](../../backend/tests/test_tencent_provider.py#L270) | 未复现新缺陷；亿转元保持有限正值；C通过 |
| 13 | 腾讯K线对齐 | [backend/tools/tencent_provider.py:168](../../backend/tools/tencent_provider.py#L168) | [backend/tests/test_tencent_provider.py:142](../../backend/tests/test_tencent_provider.py#L142) | 未复现新缺陷；日期去重排序后各数组对齐；C通过 |
| 14 | 腾讯K线日期 | [backend/tools/tencent_provider.py:168](../../backend/tools/tencent_provider.py#L168) | [backend/tests/test_tencent_provider.py:156](../../backend/tests/test_tencent_provider.py#L156) | 未复现新缺陷；非法日历观测被拒绝；C通过 |
| 15 | 腾讯K线几何 | [backend/tools/tencent_provider.py:168](../../backend/tools/tencent_provider.py#L168) | [backend/tests/test_tencent_provider.py:173](../../backend/tests/test_tencent_provider.py#L173) | 未复现新缺陷；高低价需包住开收盘；C通过 |
| 16 | 腾讯K线周期 | [backend/tools/tencent_provider.py:168](../../backend/tools/tencent_provider.py#L168) | [backend/tests/test_tencent_provider.py:223](../../backend/tests/test_tencent_provider.py#L223) | 未复现新缺陷；不把不支持周期冒充日线；C通过 |
| 17 | 腾讯分时零成交量 | [backend/tools/tencent_provider.py:302](../../backend/tools/tencent_provider.py#L302) | [backend/tests/test_tencent_provider.py:32](../../backend/tests/test_tencent_provider.py#L32) | 未复现新缺陷；零与缺失成交量语义保持；C通过 |
| 18 | 腾讯分时顺序 | [backend/tools/tencent_provider.py:302](../../backend/tools/tencent_provider.py#L302) | [backend/tests/test_tencent_provider.py:51](../../backend/tests/test_tencent_provider.py#L51) | 未复现新缺陷；排序保持最后观测及数组一致；C通过 |
| 19 | 腾讯分钟容器身份 | [backend/tools/tencent_provider.py:302](../../backend/tools/tencent_provider.py#L302) | [backend/tests/test_tencent_provider.py:98](../../backend/tests/test_tencent_provider.py#L98) | 未复现新缺陷；容器股票身份匹配；C通过 |
| 20 | 腾讯分钟时间 | [backend/tools/tencent_provider.py:302](../../backend/tools/tencent_provider.py#L302) | [backend/tests/test_tencent_provider.py:63](../../backend/tests/test_tencent_provider.py#L63) | 未复现新缺陷；非法分钟时间不能进图；C通过 |
| 21 | BaoStock登录 | [backend/tools/baostock_provider.py:40](../../backend/tools/baostock_provider.py#L40) | [backend/tests/test_baostock_provider.py:6](../../backend/tests/test_baostock_provider.py#L6) | 未复现新缺陷；登录未明确成功不查询；C通过 |
| 22 | BaoStock部分失败 | [backend/tools/baostock_provider.py:40](../../backend/tools/baostock_provider.py#L40) | [backend/tests/test_baostock_provider.py:74](../../backend/tests/test_baostock_provider.py#L74) | 未复现新缺陷；部分查询失败不能发布残留行情；C通过 |
| 23 | BaoStock代码 | [backend/tools/baostock_provider.py:40](../../backend/tools/baostock_provider.py#L40) | [backend/tests/test_baostock_provider.py:108](../../backend/tests/test_baostock_provider.py#L108) | 未复现新缺陷；跳过其他股票行；C通过 |
| 24 | BaoStock日线排序 | [backend/tools/baostock_provider.py:40](../../backend/tools/baostock_provider.py#L40) | [backend/tests/test_baostock_provider.py:36](../../backend/tests/test_baostock_provider.py#L36) | 未复现新缺陷；顺序与重复行不改变最新报价；C通过 |
| 25 | Nasdaq报价身份 | [backend/tools/us_market.py:63](../../backend/tools/us_market.py#L63) | [backend/tests/test_us_market.py:28](../../backend/tests/test_us_market.py#L28) | 未复现新缺陷；内层身份不能替换请求股票；C通过 |
| 26 | Nasdaq实时标签 | [backend/tools/us_market.py:63](../../backend/tools/us_market.py#L63) | [backend/tests/test_us_market.py:51](../../backend/tests/test_us_market.py#L51) | 未复现新缺陷；实时标记需真正的True；C通过 |
| 27 | Nasdaq图表时间 | [backend/tools/us_market.py:91](../../backend/tools/us_market.py#L91) | [backend/tests/test_us_market.py:206](../../backend/tests/test_us_market.py#L206) | 未复现新缺陷；as_of采用最后观测时间；C通过 |
| 28 | Nasdaq分时去重 | [backend/tools/us_market.py:91](../../backend/tools/us_market.py#L91) | [backend/tests/test_us_market.py:73](../../backend/tests/test_us_market.py#L73) | 未复现新缺陷；去重排序保持最新观测；C通过 |
| 29 | SEC单季口径 | [backend/tools/sec.py:229](../../backend/tools/sec.py#L229) | [backend/tests/test_sec_companyfacts_quarterly.py:45](../../backend/tests/test_sec_companyfacts_quarterly.py#L45) | 未复现新缺陷；单季跨度优先于YTD累计；C通过 |
| 30 | SEC时点数据 | [backend/tools/sec.py:229](../../backend/tools/sec.py#L229) | [backend/tests/test_sec_companyfacts_quarterly.py:65](../../backend/tests/test_sec_companyfacts_quarterly.py#L65) | 未复现新缺陷；同一报告期采用最新披露；C通过 |
| 31 | SEC概念失败 | [backend/tools/sec.py:229](../../backend/tools/sec.py#L229) | [backend/tests/test_sec_companyfacts_quarterly.py:28](../../backend/tests/test_sec_companyfacts_quarterly.py#L28) | 未复现新缺陷；坏概念不能提供财务指标；C通过 |
| 32 | SEC重复公告 | [backend/tools/sec.py:302](../../backend/tools/sec.py#L302) | [backend/tests/test_sec_tools.py:5](../../backend/tests/test_sec_tools.py#L5) | 未复现新缺陷；重复accession不挤占名额；C通过 |
| 33 | SEC公告日期 | [backend/tools/sec.py:302](../../backend/tools/sec.py#L302) | [backend/tests/test_sec_tools.py:14](../../backend/tests/test_sec_tools.py#L14) | 未复现新缺陷；非法日期不覆盖有效公告；C通过 |
| 34 | SEC CIK边界 | [backend/tools/sec.py:100](../../backend/tools/sec.py#L100) | [backend/tests/test_sec_tools.py:135](../../backend/tests/test_sec_tools.py#L135) | 未复现新缺陷；CIK须正整数且不超过十位；C通过 |
| 35 | 财表有限证据 | [backend/tools/financial.py:67](../../backend/tools/financial.py#L67) | [backend/tests/test_financial_tool_fallback.py:57](../../backend/tests/test_financial_tool_fallback.py#L57) | 未复现新缺陷；非有限值不作为财表证据；C通过 |
| 36 | 财表期间对齐 | [backend/tools/financial.py:67](../../backend/tools/financial.py#L67) | [backend/tests/test_financial_tool_fallback.py:67](../../backend/tests/test_financial_tool_fallback.py#L67) | 未复现新缺陷；期间筛选保持指标数组对应；C通过 |
| 37 | 财表失败载荷 | [backend/tools/financial.py:67](../../backend/tools/financial.py#L67) | [backend/tests/test_financial_tool_fallback.py:86](../../backend/tests/test_financial_tool_fallback.py#L86) | 未复现新缺陷；失败包不能变成成功财表；C通过 |
| 38 | 公司查询输入 | [backend/tools/financial.py:578](../../backend/tools/financial.py#L578) | [backend/tests/test_financial_tool_fallback.py:27](../../backend/tests/test_financial_tool_fallback.py#L27) | 未复现新缺陷；非文本或空查询不触发上游；C通过 |
| 39 | 股票查询去重 | [backend/tools/financial.py:578](../../backend/tools/financial.py#L578) | [backend/tests/test_financial_tool_fallback.py:175](../../backend/tests/test_financial_tool_fallback.py#L175) | 未复现新缺陷；规范化代码后去重；C通过 |
| 40 | 股票查询失败包 | [backend/tools/financial.py:578](../../backend/tools/financial.py#L578) | [backend/tests/test_financial_tool_fallback.py:167](../../backend/tests/test_financial_tool_fallback.py#L167) | 未复现新缺陷；失败包不提供匹配结果；C通过 |
| 41 | OpenFIGI筛选顺序 | [backend/tools/financial.py:665](../../backend/tools/financial.py#L665) | [backend/tests/test_financial_tool_fallback.py:109](../../backend/tests/test_financial_tool_fallback.py#L109) | 未复现新缺陷；限额应用于过滤后的唯一成功结果；C通过 |
| 42 | EODHD坏代码 | [backend/tools/financial.py:703](../../backend/tools/financial.py#L703) | [backend/tests/test_financial_tool_fallback.py:128](../../backend/tests/test_financial_tool_fallback.py#L128) | 未复现新缺陷；跳过坏行仍保留后续匹配；C通过 |
| 43 | EPS下调计数 | [backend/tools/financial.py:487](../../backend/tools/financial.py#L487) | [backend/tests/test_eps_revision_signal.py:19](../../backend/tests/test_eps_revision_signal.py#L19) | 未复现新缺陷；七天下调抵消上调；C通过 |
| 44 | 中港财表零值 | [backend/tools/cn_hk_market.py:488](../../backend/tools/cn_hk_market.py#L488) | [backend/tests/test_cn_hk_period_sort.py:44](../../backend/tests/test_cn_hk_period_sort.py#L44) | 未复现新缺陷；主值0不被回退值覆盖；C通过 |
| 45 | 中港财表重复期 | [backend/tools/cn_hk_market.py:488](../../backend/tools/cn_hk_market.py#L488) | [backend/tests/test_cn_hk_period_sort.py:31](../../backend/tests/test_cn_hk_period_sort.py#L31) | 未复现新缺陷；保留最新报告；C通过 |
| 46 | 中港全年排序 | [backend/tools/cn_hk_market.py:488](../../backend/tools/cn_hk_market.py#L488) | [backend/tests/test_cn_hk_period_sort.py:97](../../backend/tests/test_cn_hk_period_sort.py#L97) | 未复现新缺陷；FY不被期间窗口丢掉；C通过 |
| 47 | 利润行名称 | [backend/agents/fundamental_agent.py:509](../../backend/agents/fundamental_agent.py#L509) | [backend/tests/test_fundamental_metric_row_match.py:37](../../backend/tests/test_fundamental_metric_row_match.py#L37) | 未复现新缺陷；EBITDA不能抢占营业利润；C通过 |
| 48 | 营收行名称 | [backend/agents/fundamental_agent.py:509](../../backend/agents/fundamental_agent.py#L509) | [backend/tests/test_fundamental_metric_row_match.py:56](../../backend/tests/test_fundamental_metric_row_match.py#L56) | 未复现新缺陷；成本行不能抢占总收入；C通过 |
| 49 | 工作台图表身份 | [backend/dashboard/data_fetchers.py:133](../../backend/dashboard/data_fetchers.py#L133) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:62](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L62) | 未复现新缺陷；图表行股票身份必须匹配请求；C通过 |
| 50 | 工作台图表失败行 | [backend/dashboard/data_fetchers.py:133](../../backend/dashboard/data_fetchers.py#L133) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:72](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L72) | 未复现新缺陷；明确失败行不覆盖有效行情；C通过 |
| 51 | 工作台图表顺序 | [backend/dashboard/data_fetchers.py:133](../../backend/dashboard/data_fetchers.py#L133) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:82](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L82) | 未复现新缺陷；行情去重排序；C通过 |
| 52 | 工作台图表全坏行 | [backend/dashboard/data_fetchers.py:133](../../backend/dashboard/data_fetchers.py#L133) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:92](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L92) | 未复现新缺陷；全坏行返回不可用；C通过 |
| 53 | 工作台图表成交量 | [backend/dashboard/data_fetchers.py:133](../../backend/dashboard/data_fetchers.py#L133) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:102](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L102) | 未复现新缺陷；负值和布尔值不作成交量；C通过 |
| 54 | 工作台图表价格几何 | [backend/dashboard/data_fetchers.py:133](../../backend/dashboard/data_fetchers.py#L133) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:112](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L112) | 未复现新缺陷；OHLC高低范围包住开收盘；C通过 |
| 55 | 工作台图表价格数值 | [backend/dashboard/data_fetchers.py:133](../../backend/dashboard/data_fetchers.py#L133) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:123](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L123) | 未复现新缺陷；非法价格不发布；C通过 |
| 56 | 营收趋势顺序 | [backend/dashboard/data_fetchers.py:238](../../backend/dashboard/data_fetchers.py#L238) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:134](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L134) | 未复现新缺陷；未排序报告期仍按时间发布；C通过 |
| 57 | 营收构成身份 | [backend/dashboard/data_fetchers.py:282](../../backend/dashboard/data_fetchers.py#L282) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:53](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L53) | 未复现新缺陷；其他股票营收不混入；C通过 |
| 58 | 营收构成数值 | [backend/dashboard/data_fetchers.py:282](../../backend/dashboard/data_fetchers.py#L282) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:242](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L242) | 未复现新缺陷；非法金额和比例不污染结果；C通过 |
| 59 | 营收构成混合坏行 | [backend/dashboard/data_fetchers.py:282](../../backend/dashboard/data_fetchers.py#L282) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:251](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L251) | 未复现新缺陷；坏行旁的有效条目保留；C通过 |
| 60 | 行业权重边界 | [backend/dashboard/data_fetchers.py:380](../../backend/dashboard/data_fetchers.py#L380) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:226](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L226) | 未复现新缺陷；缺失或非法百分比排除；C通过 |
| 61 | 行业权重混合坏行 | [backend/dashboard/data_fetchers.py:380](../../backend/dashboard/data_fetchers.py#L380) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:233](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L233) | 未复现新缺陷；坏条目不吞有效权重；C通过 |
| 62 | 持仓股票代码 | [backend/dashboard/data_fetchers.py:429](../../backend/dashboard/data_fetchers.py#L429) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:178](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L178) | 未复现新缺陷；坏身份不挤掉有效股票；C通过 |
| 63 | 持仓零限额 | [backend/dashboard/data_fetchers.py:429](../../backend/dashboard/data_fetchers.py#L429) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:195](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L195) | 未复现新缺陷；非正限额不触发上游；C通过 |
| 64 | 持仓筛选限额 | [backend/dashboard/data_fetchers.py:429](../../backend/dashboard/data_fetchers.py#L429) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:209](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L209) | 未复现新缺陷；先过滤坏行再应用限额；C通过 |
| 65 | 成分股票代码 | [backend/dashboard/data_fetchers.py:403](../../backend/dashboard/data_fetchers.py#L403) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:187](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L187) | 未复现新缺陷；坏代码不挤掉有效成分；C通过 |
| 66 | 成分筛选限额 | [backend/dashboard/data_fetchers.py:403](../../backend/dashboard/data_fetchers.py#L403) | [backend/tests/test_dashboard_data_fetcher_boundaries.py:217](../../backend/tests/test_dashboard_data_fetcher_boundaries.py#L217) | 未复现新缺陷；先过滤再限额；C通过 |
| 67 | 估值嵌套失败 | [backend/dashboard/data_providers.py:60](../../backend/dashboard/data_providers.py#L60) | [backend/tests/test_dashboard_equity_boundaries.py:121](../../backend/tests/test_dashboard_equity_boundaries.py#L121) | 未复现新缺陷；失败metric不提供估值；C通过 |
| 68 | 估值股息率 | [backend/dashboard/data_providers.py:60](../../backend/dashboard/data_providers.py#L60) | [backend/tests/test_dashboard_equity_boundaries.py:139](../../backend/tests/test_dashboard_equity_boundaries.py#L139) | 未复现新缺陷；负值拒绝并保持合法比例；C通过 |
| 69 | 估值年度区间 | [backend/dashboard/data_providers.py:60](../../backend/dashboard/data_providers.py#L60) | [backend/tests/test_dashboard_equity_boundaries.py:160](../../backend/tests/test_dashboard_equity_boundaries.py#L160) | 未复现新缺陷；上下限正数且有序；C通过 |
| 70 | 估值市值回退 | [backend/dashboard/data_providers.py:60](../../backend/dashboard/data_providers.py#L60) | [backend/tests/test_dashboard_equity_boundaries.py:258](../../backend/tests/test_dashboard_equity_boundaries.py#L258) | 未复现新缺陷；坏profile不遮蔽有效市值；C通过 |
| 71 | 财表限额 | [backend/dashboard/data_providers.py:186](../../backend/dashboard/data_providers.py#L186) | [backend/tests/test_dashboard_equity_boundaries.py:175](../../backend/tests/test_dashboard_equity_boundaries.py#L175) | 未复现新缺陷；期间与指标均限制于请求窗口；C通过 |
| 72 | 财表指标对齐 | [backend/dashboard/data_providers.py:186](../../backend/dashboard/data_providers.py#L186) | [backend/tests/test_dashboard_equity_boundaries.py:192](../../backend/tests/test_dashboard_equity_boundaries.py#L192) | 未复现新缺陷；各指标与报告期数量对齐；C通过 |
| 73 | 财表期间形状 | [backend/dashboard/data_providers.py:186](../../backend/dashboard/data_providers.py#L186) | [backend/tests/test_dashboard_equity_boundaries.py:208](../../backend/tests/test_dashboard_equity_boundaries.py#L208) | 未复现新缺陷；坏期间容器不发布财表；C通过 |
| 74 | 财表非法数值 | [backend/dashboard/data_providers.py:186](../../backend/dashboard/data_providers.py#L186) | [backend/tests/test_dashboard_equity_boundaries.py:220](../../backend/tests/test_dashboard_equity_boundaries.py#L220) | 未复现新缺陷；非法或非有限指标成为缺失值；C通过 |
| 75 | 财表零限额 | [backend/dashboard/data_providers.py:186](../../backend/dashboard/data_providers.py#L186) | [backend/tests/test_dashboard_equity_boundaries.py:243](../../backend/tests/test_dashboard_equity_boundaries.py#L243) | 未复现新缺陷；非正限额不触发IO；C通过 |
| 76 | 财表最新期间 | [backend/dashboard/data_fetchers_equity.py:224](../../backend/dashboard/data_fetchers_equity.py#L224) | [backend/tests/test_dashboard_equity_boundaries.py:409](../../backend/tests/test_dashboard_equity_boundaries.py#L409) | 未复现新缺陷；未排序原始列仍选最新期；C通过 |
| 77 | 目标价股票身份 | [backend/dashboard/data_fetchers_equity.py:454](../../backend/dashboard/data_fetchers_equity.py#L454) | [backend/tests/test_dashboard_equity_boundaries.py:98](../../backend/tests/test_dashboard_equity_boundaries.py#L98) | 未复现新缺陷；目标价需匹配请求股票；C通过 |
| 78 | 目标价失败状态 | [backend/dashboard/data_fetchers_equity.py:454](../../backend/dashboard/data_fetchers_equity.py#L454) | [backend/tests/test_dashboard_equity_boundaries.py:112](../../backend/tests/test_dashboard_equity_boundaries.py#L112) | 未复现新缺陷；带数值的失败包仍不可用；C通过 |
| 79 | 目标价正数 | [backend/dashboard/data_fetchers_equity.py:454](../../backend/dashboard/data_fetchers_equity.py#L454) | [backend/tests/test_dashboard_equity_boundaries.py:518](../../backend/tests/test_dashboard_equity_boundaries.py#L518) | 未复现新缺陷；非正目标价格拒绝；C通过 |
| 80 | 目标价区间一致 | [backend/dashboard/data_fetchers_equity.py:454](../../backend/dashboard/data_fetchers_equity.py#L454) | [backend/tests/test_dashboard_equity_boundaries.py:533](../../backend/tests/test_dashboard_equity_boundaries.py#L533) | 未复现新缺陷；矛盾目标区间不可用；C通过 |
| 81 | 评级负计数 | [backend/dashboard/data_fetchers_equity.py:514](../../backend/dashboard/data_fetchers_equity.py#L514) | [backend/tests/test_dashboard_equity_boundaries.py:541](../../backend/tests/test_dashboard_equity_boundaries.py#L541) | 未复现新缺陷；负数不发布为分析师人数；C通过 |
| 82 | 评级小数计数 | [backend/dashboard/data_fetchers_equity.py:514](../../backend/dashboard/data_fetchers_equity.py#L514) | [backend/tests/test_dashboard_equity_boundaries.py:554](../../backend/tests/test_dashboard_equity_boundaries.py#L554) | 未复现新缺陷；人数小数不截断为整数；C通过 |
| 83 | 新闻未来时间 | [backend/dashboard/news_ranking.py:162](../../backend/dashboard/news_ranking.py#L162) | [backend/tests/test_dashboard_news_ranking.py:24](../../backend/tests/test_dashboard_news_ranking.py#L24) | 未复现新缺陷；未来时间不获最高新鲜度；C通过 |
| 84 | 新闻时间衰减 | [backend/dashboard/news_ranking.py:162](../../backend/dashboard/news_ranking.py#L162) | [backend/tests/test_dashboard_news_ranking.py:95](../../backend/tests/test_dashboard_news_ranking.py#L95) | 未复现新缺陷；半衰期参数实际生效；C通过 |
| 85 | 新闻失败条目 | [backend/dashboard/news_ranking.py:319](../../backend/dashboard/news_ranking.py#L319) | [backend/tests/test_dashboard_news_ranking.py:32](../../backend/tests/test_dashboard_news_ranking.py#L32) | 未复现新缺陷；失败行不成为可排名文章；C通过 |
| 86 | 新闻文本类型 | [backend/dashboard/news_ranking.py:319](../../backend/dashboard/news_ranking.py#L319) | [backend/tests/test_dashboard_news_ranking.py:47](../../backend/tests/test_dashboard_news_ranking.py#L47) | 未复现新缺陷；结构字段不转字符串并使用有效别名；C通过 |
| 87 | 新闻标题形状 | [backend/dashboard/news_ranking.py:319](../../backend/dashboard/news_ranking.py#L319) | [backend/tests/test_dashboard_news_ranking.py:125](../../backend/tests/test_dashboard_news_ranking.py#L125) | 未复现新缺陷；坏标题不冒充文章；C通过 |
| 88 | 新闻影响关键词 | [backend/dashboard/news_ranking.py:154](../../backend/dashboard/news_ranking.py#L154) | [backend/tests/test_dashboard_news_ranking.py:56](../../backend/tests/test_dashboard_news_ranking.py#L56) | 未复现新缺陷；影响关键词不匹配无关单词内部；C通过 |
| 89 | 新闻来源信誉 | [backend/dashboard/news_ranking.py:139](../../backend/dashboard/news_ranking.py#L139) | [backend/tests/test_dashboard_news_ranking.py:81](../../backend/tests/test_dashboard_news_ranking.py#L81) | 未复现新缺陷；仿冒子串不继承媒体信誉；C通过 |
| 90 | 新闻资产相关性 | [backend/dashboard/news_ranking.py:193](../../backend/dashboard/news_ranking.py#L193) | [backend/tests/test_dashboard_news_ranking.py:112](../../backend/tests/test_dashboard_news_ranking.py#L112) | 未复现新缺陷；股票子串不提高无关新闻权重；C通过 |
| 91 | 新闻排名限额 | [backend/dashboard/news_ranking.py:294](../../backend/dashboard/news_ranking.py#L294) | [backend/tests/test_dashboard_news_ranking.py:63](../../backend/tests/test_dashboard_news_ranking.py#L63) | 未复现新缺陷；排名在截断结果之前；C通过 |
| 92 | 新闻筛选限额 | [backend/dashboard/data_fetchers.py:310](../../backend/dashboard/data_fetchers.py#L310) | [backend/tests/test_dashboard_news_ranking.py:129](../../backend/tests/test_dashboard_news_ranking.py#L129) | 未复现新缺陷；先筛坏文章再限额；C通过 |
| 93 | 新闻全坏行 | [backend/dashboard/data_fetchers.py:310](../../backend/dashboard/data_fetchers.py#L310) | [backend/tests/test_dashboard_news_ranking.py:143](../../backend/tests/test_dashboard_news_ranking.py#L143) | 未复现新缺陷；全不可用新闻返回失败；C通过 |
| 94 | 新闻去重名额 | [backend/dashboard/data_fetchers.py:310](../../backend/dashboard/data_fetchers.py#L310) | [backend/tests/test_dashboard_news_ranking.py:153](../../backend/tests/test_dashboard_news_ranking.py#L153) | 未复现新缺陷；重复不挤掉独立文章；C通过 |
| 95 | 报告非有限证据率 | [backend/report/quality_engine.py:135](../../backend/report/quality_engine.py#L135) | [backend/tests/test_quality_engine.py:112](../../backend/tests/test_quality_engine.py#L112) | 未复现新缺陷；非有限grounding不能通过质量门禁；C通过 |
| 96 | 报告质量阈值 | [backend/report/quality_engine.py:135](../../backend/report/quality_engine.py#L135) | [backend/tests/test_quality_engine.py:96](../../backend/tests/test_quality_engine.py#L96) | 未复现新缺陷；验证器阻断采用配置阈值；C通过 |
| 97 | 报告坏引用 | [backend/report/evidence_policy.py:212](../../backend/report/evidence_policy.py#L212) | [backend/tests/test_report_validator.py:115](../../backend/tests/test_report_validator.py#L115) | 未复现新缺陷；无效证据引用被移除；C通过 |
| 98 | 报告附录覆盖 | [backend/report/evidence_policy.py:198](../../backend/report/evidence_policy.py#L198) | [backend/tests/test_report_validator.py:181](../../backend/tests/test_report_validator.py#L181) | 未复现新缺陷；附录不稀释关键正文覆盖分母；C通过 |
| 99 | 盈利历史股票身份 | [backend/dashboard/data_fetchers_equity.py:415](../../backend/dashboard/data_fetchers_equity.py#L415) | [backend/tests/test_dashboard_equity_boundaries.py:74](../../backend/tests/test_dashboard_equity_boundaries.py#L74) | 未复现新缺陷；EPS观测不混入其他股票；C通过 |
| 100 | 盈利历史失败行 | [backend/dashboard/data_fetchers_equity.py:415](../../backend/dashboard/data_fetchers_equity.py#L415) | [backend/tests/test_dashboard_equity_boundaries.py:85](../../backend/tests/test_dashboard_equity_boundaries.py#L85) | 未复现新缺陷；失败盈利行不随有效EPS发布；C通过 |
