# FinSight 脳 BettaFish 澶?Agent 鍗囩骇鍐崇瓥绋匡紙2025-12-08锛?
> 缁撹锛氬€熼壌 BettaFish 鐨勨€滀笓涓氬垎宸?+ 璁哄潧寮忓崗浣?+ 鍙嶆€?+ IR鈥濓紝鍒嗕笁姝ヨ惤鍦帮細鍏堟妸宸ュ叿缂撳瓨涓庣粨鏋勫寲杈撳嚭鎵撶墷锛屽啀鎺ュ叆 3-4 涓瓙 Agent 涓庤交閲忚鍧涜仛鍚堬紝鏈€鍚庤ˉ鍙嶆€濆惊鐜笌 IR/RAG锛岄伩鍏嶄竴娆℃€ч噸鏋勫け鎺с€?
---

## A. BettaFish 瑕佺偣锛堢敤浜庡榻愶級
- 涓撲笟鍒嗗伐锛歈uery/Media/Insight/Report锛孎orumHost 鏀舵暃涓庤京璁恒€?- 璁哄潧寮忓崗浣滐細Agent 閫氳繃 forum.log 寮傛浜ゆ祦锛屼富鎸佷汉鎻愪緵鏃堕棿绾?瑙傜偣鏁村悎/娣卞害鍒嗘瀽/鎸囧紩銆?- 鍙嶆€濆惊鐜細姣忎釜 Agent 2-3 杞€滆瘑鍒┖鐧?鈫?瀹氬悜琛ユ悳 鈫?鏇存柊鎬荤粨鈥濄€?- 楂樺彫鍥?+ 缂撳瓨锛氬婧愭悳绱?鐖櫕 鈫?2-5 鍙ユ憳瑕?+ Markdown 閾炬帴 鈫?KV/Redis 缂撳瓨澶嶇敤銆?- IR 杈撳嚭锛氬悇 Agent 鎶ュ憡 + forum 鍐呭 鈫?妯℃澘鍖栨覆鏌?HTML/PDF锛孖R 鍙牎楠?鍥炴函銆?
## B. FinSight 鐜扮姸锛堝叧閿樊璺濓級
- 鍗?CIO Agent + Router锛涙棤鏄惧紡瀛?Agent 鍒嗗伐涓庤鍧?杈╄銆?- 宸ュ叿灞傞檺娴佸銆佺紦瀛?鍏滃簳钖勫急锛涚己缁熶竴鏃ュ織瀛楁锛坰ource/duration/fail_reason/fallback_used锛夈€?- 闀挎枃鎶ュ憡鏃?IR锛屽墠绔毦缁撴瀯鍖栧睍绀猴紱鍙娴嬫€т笉瓒炽€?
---

## C. 鏈€缁堣矾绾匡紙涓夐樁娈碉級

### 闃舵 0锛? 鍛級锛氱ǔ鎬佸熀搴?+ 缁撴瀯鍖栬緭鍑?- `backend/tools.py`锛氱粺涓€杩斿洖缁撴瀯 `value/as_of/source/fallback_used/fail_reason`锛岃ˉ 30-60s 鐭紦瀛樹笌鍙厤缃紭鍏堢骇锛涙悳绱㈠厹搴曪紙Tavily/Serper/DDG锛岄檺鏃讹級銆?- `backend/langchain_agent.py`锛氳緭鍑?`observations/risks/recommendation` 缁撴瀯锛涜缃?`max_iterations/timeout`锛岃妭鐐规墦 tracing tag銆?- `backend/api/main.py`锛氱粺涓€閿欒鍖呰锛岄€忓嚭 `data_origin/fallback_used`锛屽仴搴锋鏌ュ睍绀?fail_rate銆?- 鍓嶇锛欴iagnostics 闈㈡澘灞曠ず宸ュ叿璋冪敤椤哄簭銆佽€楁椂銆佸け璐ュ師鍥犮€並V 鍛戒腑/閲嶆悳鏍囪銆?- 鏂囨。锛氫繚鐣欐棫钃濆浘锛屾柊澧炴湰鍐崇瓥绋块摼鎺ワ紙鐘舵€侀〉锛夈€?
### 闃舵 1锛?-3 鍛級锛氬瓙 Agent + 杞婚噺璁哄潧鑱氬悎
- 鐩綍锛歚backend/agents/{base,technical,fundamental,macro,sentiment,orchestrator}.py`
- `AgentOutput` 缁熶竴 schema锛坰ummary/evidence/links/confidence/as_of/risks/data_sources锛夈€?- Orchestrator锛圠angGraph 涓诲浘锛夛細骞惰璋冪敤 3-4 瀛?Agent锛屽仛鍘婚噸/鍐茬獊娑堣В锛涜交閲?`AgentForum`锛堝唴瀛橀槦鍒楋級璁板綍鍚?Agent 鍙戠幇锛屼緵浜掔浉鍙傝€冦€?- DeepSearch 瑙﹀彂锛氬伐鍏蜂笉瓒?杩囨湡鏃惰皟鐢?news/sentiment Agent锛岄珮鍙洖鎽樿 + 鍐?KV锛坱icker+field+as_of锛孴TL锛夈€?- E2E 鐢ㄤ緥锛氳鎯呭け璐モ啋鎼滅储鍏滃簳鎴愬姛锛沶ews KV 鍛戒腑锛涘吀鍨嬮棶绛旇Е鍙?鈮? 涓瓙 Agent銆?- 鍓嶇锛氬璇濇皵娉℃梺鏍囪鈥滅敱鍝簺 Agent 璐＄尞鈥濓紝鎻愮ず鍏滃簳鏉ユ簮銆?
### 闃舵 2锛?-6 鍛級锛氬弽鎬濆惊鐜?+ IR/RAG
- 鍙嶆€濓細鍦ㄥ瓙 Agent 鍐呭鍔?1-2 杞€滆瘑鍒┖鐧?鈫?瀹氬悜琛ユ悳 鈫?鏇存柊鎬荤粨鈥濓紝楂樻垚鏈矾寰勫彈闄愭椂闀裤€?- IR锛歚backend/report/ir.py` 瀹氫箟 IR Schema + 鏍￠獙鍣紱Orchestrator 鍚堝苟 AgentOutput 鈫?IR 鈫?Markdown/HTML锛圥DF 鍙悗缃級銆?- RAG锛氶暱鏂?鐮旀姤鎽樿鍒囧垎鍏ュ悜閲忓簱锛屾姤鍛婂墠鍏堟绱㈢墖娈碉紝鍐嶈ˉ瀹炴椂宸ュ叿銆?- 璁哄潧寮哄寲锛氬彲閫夎惤鍦?forum.log 鏂囦欢鎴栬瘖鏂潰鏉匡紝淇濈暀涓绘寔浜哄紡寮曞锛堝彲鐢ㄦ洿灏忔ā鍨嬶級銆?
---

## D. 鍏抽敭瀹炵幇娓呭崟锛堟枃浠剁骇鎸囧紩锛?- 缂撳瓨涓庡厹搴曪細`backend/services/cache.py`锛堢煭 TTL 鍐呭瓨缂撳瓨锛夛紝`backend/tools.py`锛坰ource/duration/fail_reason/fallback_used锛夛紝鎸囨暟鍗曠嫭浼樺厛绾ц〃銆?- 瀛?Agent锛歚backend/agents/base_agent.py`锛圓gentOutput dataclass +鏍￠獙锛夛紱`technical_agent.py`锛坓et_stock_price/kline/鎸囨爣锛夛紱`fundamental_agent.py`锛堣储鎶?浼板€?缁忚惀瑕佺偣锛夛紱`macro_agent.py`锛堟棩鍘?鍒╃巼/鎯呯华锛夛紱`sentiment_agent.py`锛堟柊闂?Tavily/绀句氦锛夛紱`orchestrator.py`锛堝苟琛?鍐茬獊娑堣В+forum锛夈€?- 鍙嶆€濓細鍦ㄥ悇 Agent 鍐呭鍔?`_reflection_loop` 閽╁瓙锛堝彲閰嶇疆 max_rounds锛夛紝浠呭湪鎶ュ憡/娣卞害妯″紡鍚敤銆?- IR锛歚backend/report/ir.py`锛坰chema+鏍￠獙锛夛紝`handlers/report_handler.py` 灏嗗悎骞?state 娓叉煋 Markdown/HTML銆?- 鍙娴嬫€э細`logs/diagnostics.log` 缁撴瀯鍖?JSON锛涘墠绔?Diagnostics 闈㈡澘璇诲彇 `data_origin/fallback_used/agent_contributors`銆?
---

## E. 楠屾敹鏍囧噯锛堟寜闃舵锛?- 闃舵 0锛氬伐鍏峰け璐ヤ笉 500锛汥iagnostics 鍙 data_origin/fallback锛涙悳绱㈠厹搴曞彲鐢紱KV 鍛戒腑/杩囨湡閲嶆悳鍙瀵熴€?- 闃舵 1锛氬吀鍨嬫煡璇㈣Е鍙?鈮? 瀛?Agent锛涜緭鍑烘寜 AgentOutput 鍒嗙淮搴﹀憟鐜帮紝鍚摼鎺ヤ笌 as_of锛汥eepSearch 缂哄彛鍦烘櫙鑳借ˉ鏁版嵁銆?- 闃舵 2锛氬弽鎬濆惊鐜兘鍑忓皯缂洪」锛汭R 鏍￠獙閫氳繃鐜?>95%锛涙姤鍛婂彲婧簮寮曠敤锛堢墖娈?鏉ユ簮锛夈€?
---

## F. 绔嬪嵆琛屽姩锛堜粖鏃ヨ捣锛?1) 杩藉姞鐭紦瀛樹笌鏃ュ織瀛楁锛歚backend/tools.py`銆乣backend/langchain_agent.py`锛汚PI 閫忓嚭 `data_origin/fallback_used`銆?
2) 鍒涘缓 `backend/agents/` 鐩綍涓?`AgentOutput` 鍩虹被锛屾帴鍏?Technical/Fundamental 涓や釜鏈€灏忓瓙 Agent锛汷rchestrator 骞惰铻嶅悎銆?
3) 鍓嶇 Diagnostics 闈㈡澘鏄剧ず鈥滄暟鎹潵婧?鍏滃簳/Agent 璐＄尞鈥濓紱鏂囨。鍦?`docs/plans/Future_Blueprint_Execution_Plan_CN.md` 閾炬帴鏈喅绛栫銆?
4) 鏂板 E2E 鐢ㄤ緥瑕嗙洊琛屾儏鍏滃簳涓庡 Agent 鏈€灏忚矾寰勩€?
