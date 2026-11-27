package fogsim.adapter;

import ec.*;
import ec.gp.*;
import mengxu.gp.data.DoubleData;
import mengxu.gp.terminal.*;
import mengxu.gp.function.*;
import mengxu.rule.*;
import mengxu.rule.evolved.GPRule;
import mengxu.algorithm.FCFS;
import mengxu.simulation.state.SystemState;
import mengxu.taskscheduling.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.regex.Pattern;

/** Independent frozen-language frontend. Execution delegates to original GPNode.eval. */
public final class StageDGP {
    static final String ID="fogsim-rule-identity-v1",LANG="fogsim-gp-lisp-v1",FEATURES="fogsim-features-java-v1",SELECT="fogsim-selection-java-v1";
    static final String NUM=Boolean.getBoolean("fogsim.stage_d.original")?"java-original-positive-zero-v1":"fogsim-gp-f64-dual-zero-v1";
    static final String[] FEATURE_NAMES={"NIQ","WIQ","MRT","UT","DT","PT","TTIQ","TIS","TWT","NTR"};
    static final Set<String> FEATURE_SET=Set.of(FEATURE_NAMES), OPS=Set.of("+","-","*","/","Max","Min");
    static final Pattern NUMBER=Pattern.compile("-?(?:0[0-7]+|(?:(?:0|[1-9][0-9]*)(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?[dDfF]?)");
    static Map<String,Object> map(Object...a){Map<String,Object>m=new LinkedHashMap<>();for(int i=0;i<a.length;i+=2)m.put((String)a[i],a[i+1]);return m;}
    static Map<String,Object> obj(Object a){return FixedInstanceMain.obj(a);}
    static List<Object> list(Object a){return FixedInstanceMain.list(a);}
    static String str(Object a){if(!(a instanceof String))throw new IllegalArgumentException("expected string");return (String)a;}
    static String hex(double x){return String.format(Locale.ROOT,"%016x",Double.doubleToRawLongBits(x));}
    static Map<String,Object> tag(double x){return map("kind","f64","bits",hex(x));}
    static double f64(Object x){Map<String,Object>m=obj(x);if(!m.keySet().equals(Set.of("kind","bits"))||!"f64".equals(m.get("kind"))||!(m.get("bits") instanceof String)||!str(m.get("bits")).matches("[0-9a-f]{16}"))throw new IllegalArgumentException("GP_F64_ENCODING_INVALID");return Double.longBitsToDouble(Long.parseUnsignedLong(str(m.get("bits")),16));}
    static String sha(byte[] b){try{byte[] d=MessageDigest.getInstance("SHA-256").digest(b);StringBuilder s=new StringBuilder();for(byte x:d)s.append(String.format(Locale.ROOT,"%02x",x&255));return s.toString();}catch(Exception e){throw new IllegalStateException(e);}}
    static String sourceSha(String s){return "sha256:"+sha(s.getBytes(StandardCharsets.UTF_8));}
    static void cjString(String s,StringBuilder b){
        b.append('"');for(int i=0;i<s.length();i++){char c=s.charAt(i);
            if(Character.isHighSurrogate(c)){if(i+1>=s.length()||!Character.isLowSurrogate(s.charAt(i+1)))throw new IllegalArgumentException("unpaired surrogate");}
            else if(Character.isLowSurrogate(c)&&(i==0||!Character.isHighSurrogate(s.charAt(i-1))))throw new IllegalArgumentException("unpaired surrogate");
            switch(c){case '"':b.append("\\\"");break;case '\\':b.append("\\\\");break;case '\b':b.append("\\b");break;case '\f':b.append("\\f");break;case '\n':b.append("\\n");break;case '\r':b.append("\\r");break;case '\t':b.append("\\t");break;default:if(c<32||c>=127)b.append(String.format(Locale.ROOT,"\\u%04x",(int)c));else b.append(c);}
        }b.append('"');
    }
    static void cjValue(Object a,StringBuilder b){
        if(a instanceof String){cjString((String)a,b);return;}
        if(a instanceof Integer||a instanceof Long){if(((Number)a).longValue()<0)throw new IllegalArgumentException("CJ negative integer");b.append(a);return;}
        if(a instanceof List){b.append('[');boolean first=true;for(Object x:(List<?>)a){if(!first)b.append(',');first=false;cjValue(x,b);}b.append(']');return;}
        if(a instanceof Map){TreeMap<String,Object>m=new TreeMap<>();for(Map.Entry<?,?> e:((Map<?,?>)a).entrySet()){if(!(e.getKey() instanceof String)||!((String)e.getKey()).chars().allMatch(c->c<128))throw new IllegalArgumentException("CJ ASCII keys required");m.put((String)e.getKey(),e.getValue());}b.append('{');boolean first=true;for(Map.Entry<String,Object>e:m.entrySet()){if(!first)b.append(',');first=false;cjString(e.getKey(),b);b.append(':');cjValue(e.getValue(),b);}b.append('}');return;}
        throw new IllegalArgumentException("CJ accepts objects, arrays, strings and nonnegative integers");
    }
    static String cj(Object a){StringBuilder b=new StringBuilder();cjValue(a,b);return b.toString();}
    static String digest(String domain,Object payload){return "sha256:"+sha((domain+"\n"+cj(payload)).getBytes(StandardCharsets.UTF_8));}
    static final class ParseError extends IllegalArgumentException {final Map<String,Object> diagnostic;ParseError(Map<String,Object>d){super(str(d.get("code")));diagnostic=d;}}
    static ParseError error(String text,String role,String path,String code,String message,int start,int end){
        int line=1,column=1,i=0;while(i<start){char c=text.charAt(i);if(c=='\r'&&i+1<text.length()&&text.charAt(i+1)=='\n'){if(i+1==start)break;i+=2;line++;column=1;}else if(c=='\r'||c=='\n'){i++;line++;column=1;}else{i++;column++;}}
        // Invalid Unicode is rejected lexically; positions count Unicode code points, not UTF-16 units.
        int cpStart=text.codePointCount(0,start),cpEnd=text.codePointCount(0,end);
        return new ParseError(map("code",code,"message",message,"field_path",path,"role",role,"token",text.substring(start,end),"start",cpStart,"end",cpEnd,"line",line,"column",column));
    }
    record Token(String text,int start,int end){}
    static final class Frame {String op;List<GPNode> children=new ArrayList<>();}
    static boolean white(char c){return " \t\n\u000b\f\r".indexOf(c)>=0;}
    static boolean allowed(char c){return c<128&&(Character.isLetterOrDigit(c)||"+-*/._()".indexOf(c)>=0||white(c));}
    static GPNode op(String s){switch(s){case "+":return new Add();case "-":return new Sub();case "*":return new Mul();case "/":return new Div();case "Max":return new Max();case "Min":return new Min();default:throw new IllegalArgumentException("unknown function");}}
    static final class ReadFeature extends AttributeGPNode {
        ReadFeature(String name){super(JobShopAttribute.get(name));}
        @Override public void eval(EvolutionState s,int t,GPData d,ADFStack a,GPIndividual i,Problem p){super.eval(s,t,d,a,i,p);observe(this,((DoubleData)d).value);}
    }
    static final class ReadConstant extends DoubleERC {
        ReadConstant(double d){value=d;children=new GPNode[0];}
        @Override public void eval(EvolutionState s,int t,GPData d,ADFStack a,GPIndividual i,Problem p){super.eval(s,t,d,a,i,p);observe(this,((DoubleData)d).value);}
    }
    static final ThreadLocal<List<Object>> READS=new ThreadLocal<>();
    static final ThreadLocal<IdentityHashMap<GPNode,Integer>> NODE_IDS=new ThreadLocal<>();
    static void observe(GPNode node,double value){if(READS.get()!=null)READS.get().add(map("node_index",NODE_IDS.get().get(node),"kind",node instanceof AttributeGPNode?"feature":"constant","name",node instanceof AttributeGPNode?((AttributeGPNode)node).getJobShopAttribute().getName():"constant","value",tag(value)));}
    static GPNode parse(String text,String role,String path){
        for(int i=0;i<text.length();i++)if(!allowed(text.charAt(i))){int end=i+Character.charCount(text.codePointAt(i));throw error(text,role,path,"GP_INVALID_CHARACTER","character is not permitted in the GP language",i,end);}
        List<Token> ts=new ArrayList<>();for(int i=0;i<text.length();){if(white(text.charAt(i))){i++;continue;}int start=i;if(text.charAt(i)=='('||text.charAt(i)==')')i++;else while(i<text.length()&&!white(text.charAt(i))&&text.charAt(i)!='('&&text.charAt(i)!=')')i++;ts.add(new Token(text.substring(start,i),start,i));}
        if(ts.isEmpty())throw error(text,role,path,"GP_EMPTY_EXPRESSION","expression is empty",text.length(),text.length());
        Deque<Frame> stack=new ArrayDeque<>();GPNode root=null;
        for(Token token:ts){String s=token.text();
            if(root!=null&&stack.isEmpty())throw error(text,role,path,"GP_TRAILING_INPUT","expected the end of the expression",token.start(),token.end());
            if(!stack.isEmpty()&&stack.peek().op==null){if(!OPS.contains(s))throw error(text,role,path,"GP_UNKNOWN_FUNCTION","expected one of the six binary functions",token.start(),token.end());stack.peek().op=s;continue;}
            GPNode node;
            if(s.equals(")")){
                if(stack.isEmpty())throw error(text,role,path,"GP_UNBALANCED_PARENTHESES","closing parenthesis has no open call",token.start(),token.end());
                Frame f=stack.pop();if(f.children.size()!=2)throw error(text,role,path,"GP_ARITY_ERROR","a function requires exactly two expressions",token.start(),token.end());
                node=op(f.op);node.children=f.children.toArray(new GPNode[0]);for(int j=0;j<2;j++){node.children[j].parent=node;node.children[j].argposition=(byte)j;}
            }else{
                if(!stack.isEmpty()&&stack.peek().children.size()==2)throw error(text,role,path,"GP_ARITY_ERROR","a function has more than two expressions",token.start(),token.end());
                if(s.equals("(")){stack.push(new Frame());continue;}
                if(NUMBER.matcher(s).matches()){String n="dDfF".indexOf(s.charAt(s.length()-1))>=0?s.substring(0,s.length()-1):s;node=new ReadConstant(Double.parseDouble(n));}
                else if("+-.0123456789".indexOf(s.charAt(0))>=0)throw error(text,role,path,"GP_INVALID_CONSTANT","constant does not match the frozen number grammar",token.start(),token.end());
                else if(FEATURE_SET.contains(s))node=new ReadFeature(s);
                else throw error(text,role,path,"GP_UNKNOWN_FEATURE","expected one of the ten features or a valid constant",token.start(),token.end());
            }
            if(stack.isEmpty())root=node;else stack.peek().children.add(node);
        }
        if(!stack.isEmpty())throw error(text,role,path,"GP_UNBALANCED_PARENTHESES","end of input in an unclosed call",text.length(),text.length());return root;
    }
    static List<GPNode> nodes(GPNode root){List<GPNode> out=new ArrayList<>();Deque<GPNode> q=new ArrayDeque<>();q.push(root);while(!q.isEmpty()){GPNode n=q.pop();out.add(n);for(int i=n.children.length-1;i>=0;i--)q.push(n.children[i]);}return out;}
    static Map<String,Object> ast(GPNode root){List<GPNode>ns=nodes(root);IdentityHashMap<GPNode,Integer>ids=new IdentityHashMap<>();for(int i=0;i<ns.size();i++)ids.put(ns.get(i),i);List<Object>out=new ArrayList<>();for(GPNode n:ns){if(n instanceof AttributeGPNode)out.add(map("kind","feature","name",((AttributeGPNode)n).getJobShopAttribute().getName()));else if(n instanceof DoubleERC)out.add(map("kind","constant","bits",hex(((DoubleERC)n).value)));else out.add(map("kind","binary","op",n.toString(),"left",ids.get(n.children[0]),"right",ids.get(n.children[1])));}return map("root",0,"nodes",out);}
    static Map<String,Object> expression(GPNode root){Map<String,Object>e=map("identity_encoding_version",ID,"language_version",LANG,"feature_semantics_version",FEATURES,"numeric_semantics_version",NUM,"ast",ast(root));Map<String,Object>r=new LinkedHashMap<>(e);r.put("expression_id",digest("fogsim.expression-id.v1",e));return r;}
    static final class Prepared {
        final Map<String,Object> manifest;final Map<String,AbstractRule> rules=new LinkedHashMap<>();final Map<String,GPNode> roots=new LinkedHashMap<>();
        Prepared(Map<String,Object>routing,Map<String,Object>sequencing){Map<String,Object>bindings=new LinkedHashMap<>();TreeMap<String,Object>expressions=new TreeMap<>();
            for(String role:List.of("routing","sequencing")){Map<String,Object>s=role.equals("routing")?routing:sequencing;String kind=str(s.get("kind"));RuleType type=role.equals("routing")?RuleType.ROUTING:RuleType.SEQUENCING;
                Set<String>keys=kind.equals("gp")?Set.of("kind","expression"):kind.equals("fixed_resource")?Set.of("kind","resource_id"):Set.of("kind");
                if(!s.keySet().equals(keys)||!Set.of("gp","fcfs","fixed_resource").contains(kind)||role.equals("sequencing")&&kind.equals("fixed_resource"))throw new IllegalArgumentException("GP_RULE_SPEC_INVALID");
                Map<String,Object>p=map("identity_encoding_version",ID,"role",role,"kind",kind,"selection_policy_version",SELECT);GPNode root=null;String text=null;
                if(kind.equals("gp")){text=str(s.get("expression"));root=parse(text,role,role+"_rule.expression");GPTree tree=new GPTree();tree.child=root;root.parent=tree;root.argposition=0;rules.put(role,new GPRule(type,tree,text));roots.put(role,root);Map<String,Object>e=expression(root);String eid=str(e.get("expression_id"));expressions.put(eid,e);p.put("expression_id",eid);}
                else if(kind.equals("fcfs")){p.put("baseline_semantics_version","fogsim-fcfs-v1");rules.put(role,new FCFS(type));}
                else{String target=str(s.get("resource_id"));if(target.trim().isEmpty())throw new IllegalArgumentException("empty target");p.put("baseline_semantics_version","fogsim-fixed-resource-v1");p.put("resource_id",target);rules.put(role,new FixedRule(type,target));}
                Map<String,Object>b=new LinkedHashMap<>(p);b.put("rule_id",digest("fogsim.rule-id.v1",p));if(root!=null){b.remove("identity_encoding_version");b.put("source",map("expression",text,"source_sha256",sourceSha(text)));}bindings.put(role,b);
            }
            Map<String,Object>pair=map("identity_encoding_version",ID,"routing_rule_id",obj(bindings.get("routing")).get("rule_id"),"sequencing_rule_id",obj(bindings.get("sequencing")).get("rule_id"));
            manifest=map("identity_encoding_version",ID,"expressions",new ArrayList<>(expressions.values()),"bindings",bindings,"rule_pair_id",digest("fogsim.rule-pair-id.v1",pair));
        }
        void begin(String role){GPNode root=roots.get(role);IdentityHashMap<GPNode,Integer>ids=new IdentityHashMap<>();if(root!=null){List<GPNode>ns=nodes(root);for(int i=0;i<ns.size();i++)ids.put(ns.get(i),i);}NODE_IDS.set(ids);READS.set(new ArrayList<>());}
        List<Object>end(){List<Object>r=READS.get();READS.remove();NODE_IDS.remove();return r;}
    }
    static final IdentityHashMap<Object,String> RESOURCE_IDS=new IdentityHashMap<>();
    static final class FixedRule extends AbstractRule {final String target;FixedRule(RuleType t,String s){type=t;target=s;}public double priority(TaskOption o,Server s,SystemState state){Object r=o.getServer()==null?o.getMobileDevice():o.getServer();return target.equals(RESOURCE_IDS.get(r))?0.0:1.0;}}
}
