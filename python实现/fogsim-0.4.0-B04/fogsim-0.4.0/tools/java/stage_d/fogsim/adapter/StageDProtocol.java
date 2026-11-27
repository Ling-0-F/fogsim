package fogsim.adapter;
import static fogsim.adapter.StageDGP.*;
import java.util.*;

/** Explicit score fields, never a recursive conversion of physical numbers. */
final class StageDProtocol {
    static Object score(Object v){if(v instanceof Map){f64(v);return v;}return tag(((Number)v).doubleValue());}
    static void fixedState(Map<String,Object>s){for(Object t:list(s.get("tasks")))for(Object o:list(obj(t).get("options"))){Map<String,Object>v=obj(o);v.put("priority",score(v.get("priority")));}}
    static void fixedDecision(Map<String,Object>d){for(Object o:list(d.get("candidates"))){Map<String,Object>v=obj(o);v.put("priority",score(v.get("priority")));}}
    static void fixedResult(Map<String,Object>r){for(Object d:list(r.get("decisions")))fixedDecision(obj(d));for(Object item:list(r.get("events"))){Map<String,Object>e=obj(item);fixedState(obj(e.get("before")));fixedState(obj(e.get("after")));for(Object a:list(e.get("actions")))if("DECISION".equals(obj(a).get("kind")))fixedDecision(obj(obj(a).get("decision")));}}
    static Map<String,Object> envelope(String kind,Map<String,Object>manifest,Object payload,Object coverage){return map("format","fogsim.gp-reference","schema_version",2,"reference_kind",kind,"score_encoding_version","ieee754-binary64-hex-v1","rule_manifest",manifest,"payload",payload,"coverage",coverage,"provenance",map("language","Java","numeric_semantics_version",NUM,"java_runtime",System.getProperty("java.runtime.version"),"java_vendor",System.getProperty("java.vendor"),"source_fingerprint",System.getProperty("fogsim.stage_d.source"),"build_manifest_sha256",System.getProperty("fogsim.stage_d.build"),"implementation","original GPNode.eval / AbstractRule selection; audited overlay only"));}
}
