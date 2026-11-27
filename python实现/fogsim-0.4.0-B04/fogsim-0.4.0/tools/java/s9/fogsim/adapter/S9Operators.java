package fogsim.adapter;

import ec.*;
import ec.gp.*;
import ec.gp.koza.*;
import ec.select.TournamentSelection;
import ec.breed.MultiBreedingPipeline;
import ec.simple.SimpleFitness;
import ec.util.*;
import mengxu.gp.GPRuleEvolutionState;
import mengxu.gp.terminal.*;
import java.nio.file.*;
import java.util.*;

/** Controlled inputs only. Original ECJ builders, selectors and pipelines execute. */
public class S9Operators {
    static final String[] FEATURES={"NIQ","WIQ","MRT","UT","DT","PT","TTIQ","TIS","TWT","NTR"};
    static final String[] OPS={"+","-","*","/","Max","Min"};
    static Map m(Object o){return (Map)o;}
    static int num(Object o){return ((Number)o).intValue();}
    static Map<String,Object> map(Object... kv){Map<String,Object> out=new LinkedHashMap<>();for(int i=0;i<kv.length;i+=2)out.put((String)kv[i],kv[i+1]);return out;}
    static class Controlled extends MersenneTwisterFast {
        ArrayDeque<Integer> ints=new ArrayDeque<>();ArrayDeque<Double> reals=new ArrayDeque<>();List<Object> calls=new ArrayList<>();
        Controlled(List<?> a,List<?> b){super(19);for(Object v:a)ints.add(num(v));for(Object v:b)reals.add(((Number)v).doubleValue());}
        public int nextInt(int n){int x=n==1?0:ints.remove();if(x<0||x>=n)throw new IllegalArgumentException("draw out of bounds "+n+":"+x);calls.add(map("bound",n,"value",x));return x;}
        public double nextDouble(){double x=reals.remove();calls.add(map("double",x));return x;}
        public boolean nextBoolean(double p){if(p==1)return true;if(p==0)return false;return nextDouble()<p;}
    }
    static void field(Object o,Class<?> cls,String key,Object value){try{var f=cls.getDeclaredField(key);f.setAccessible(true);f.set(o,value);}catch(Exception e){throw new RuntimeException(e);}}
    static class EliteBreeder extends ec.simple.SimpleBreeder {
        void load(EvolutionState s,Population p){elite=new int[]{1};eliteFrac=new double[]{0};reevaluateElites=new boolean[]{true};loadElites(s,p);}
    }
    static class ObservedEvaluator extends Evaluator {
        int calls;
        public void evaluatePopulation(EvolutionState s){calls++;}
        public boolean runComplete(EvolutionState s){return false;}
        public void evaluatePopulation(EvolutionState s,Population p){calls++;}
    }
    static GPRuleEvolutionState state(Controlled rng){
        GPRuleEvolutionState s=new GPRuleEvolutionState();s.random=new MersenneTwisterFast[]{rng};
        s.output=new Output(true);GPInitializer init=new GPInitializer();s.initializer=init;
        GPAtomicType t=new GPAtomicType();t.type=0;init.types=new GPType[]{t};init.numAtomicTypes=1;
        GPNodeConstraints bin=new GPNodeConstraints();bin.returntype=t;bin.childtypes=new GPType[]{t,t};
        GPNodeConstraints term=new GPNodeConstraints();term.returntype=t;term.childtypes=new GPType[0];
        init.nodeConstraints=new GPNodeConstraints[]{bin,term};
        GPTreeConstraints tc=new GPTreeConstraints();tc.treetype=t;init.treeConstraints=new GPTreeConstraints[]{tc};
        GPNode[] features=new GPNode[10];for(int i=0;i<10;i++){features[i]=new AttributeGPNode(JobShopAttribute.get(FEATURES[i]));features[i].children=new GPNode[0];features[i].constraints=1;}
        s.setTerminals(new GPNode[][]{features});
        GPFunctionSet fs=new GPFunctionSet();fs.name="controlled0";
        GPNode[] fns=new GPNode[6];for(int i=0;i<6;i++){fns[i]=StageDGP.op(OPS[i]);fns[i].children=new GPNode[2];fns[i].constraints=0;}
        TerminalERCUniform terminal=new TerminalERCUniform();terminal.children=new GPNode[0];terminal.constraints=1;
        fs.terminals=new GPNode[][]{{terminal}};fs.nonterminals=new GPNode[][]{fns};GPNode[] all=Arrays.copyOf(fns,7);all[6]=terminal;fs.nodes=new GPNode[][]{all};tc.functionset=fs;
        return s;
    }
    static GPIndividual individual(String expr){
        GPIndividual i=new GPIndividual();GPTree tree=new GPTree();tree.owner=i;tree.constraints=0;tree.child=StageDGP.parse(expr,"routing","expression");tree.child.parent=tree;tree.child.argposition=0;
        ArrayList<GPNode> list=new ArrayList<>();walk(tree.child,list);for(GPNode n:list)n.constraints=(byte)(n.children.length==0?1:0);
        i.trees=new GPTree[]{tree};i.fitness=new SimpleFitness();return i;
    }
    static void walk(GPNode n,List<GPNode> list){list.add(n);for(GPNode c:n.children)walk(c,list);}
    static GPNode at(GPTree tree,int index){return tree.child.nodeInPosition(index,GPNode.NODESEARCH_ALL);}
    static String expression(GPNode n){if(n.children.length==0)return n.toString();return "("+n.toString()+" "+expression(n.children[0])+" "+expression(n.children[1])+")";}
    static class FixedSelector extends KozaNodeSelector {
        int[] positions;int at;FixedSelector(List<?> p){positions=p.stream().mapToInt(S9Operators::num).toArray();}
        public GPNode pickNode(EvolutionState s,int sp,int th,GPIndividual ind,GPTree tree){return S9Operators.at(tree,positions[at++]);}
    }
    static class FixedSource extends SelectionMethod {
        GPIndividual[] choices;int at;
        FixedSource(GPIndividual... c){choices=c;}
        public Parameter defaultBase(){return new Parameter("controlled");}
        public int produce(int sp,EvolutionState s,int t){return 0;}
        public int produce(int min,int max,int start,int sp,Individual[] out,EvolutionState s,int t){for(int k=0;k<min;k++)out[start+k]=choices[(at++)%choices.length];return min;}
    }
    static class Cross extends CrossoverPipeline {void parents(){parents=new GPIndividual[2];}}
    static class FixedBuilder extends GPNodeBuilder {
        String expr;FixedBuilder(String e){expr=e;}
        public Parameter defaultBase(){return new Parameter("controlled");}
        public GPNode newRootedTree(EvolutionState s,GPType t,int th,GPNodeParent p,GPFunctionSet fs,int a,int size){GPNode n=individual(expr).trees[0].child;n.parent=p;n.argposition=(byte)a;return n;}
    }
    static class CountSource extends BreedingSource {
        int count;String label;CountSource(String name,int n,double p){label=name;count=n;probability=p;}
        public Parameter defaultBase(){return new Parameter("controlled");}
        public int typicalIndsProduced(){return count;}
        public boolean produces(EvolutionState s,Population p,int sp,int th){return true;}
        public void prepareToProduce(EvolutionState s,int sp,int th){}
        public void finishProducing(EvolutionState s,int sp,int th){}
        public int produce(int min,int max,int start,int sp,Individual[] out,EvolutionState s,int th){return Math.min(max,Math.max(min,count));}
        public int produceFrac(int min,int max,int start,int sp,Individual[] out,EvolutionState s,int th){return produce(min,max,start,sp,out,s,th);}
    }
    static Object run(Map c){
        String kind=(String)c.get("kind");Controlled rng=new Controlled((List)c.getOrDefault("ints",List.of()),(List)c.getOrDefault("reals",List.of()));GPRuleEvolutionState s=state(rng);GPInitializer init=(GPInitializer)s.initializer;
        if(kind.equals("generate")){
            HalfBuilder builder=new HalfBuilder();builder.minDepth=builder.maxDepth=num(c.get("height"))+1;builder.pickGrowProbability=c.get("method").equals("grow")?1:0;
            GPNode root=builder.newRootedTree(s,init.types[0],0,new GPTree(),init.treeConstraints[0].functionset,0,-1);
            return map("expression",expression(root),"height",root.depth()-1,"nodes",root.numNodes(GPNode.NODESEARCH_ALL),"random_calls",rng.calls);
        }
        if(kind.equals("tournament")){
            List<?> values=(List)c.get("fitnesses");Individual[] inds=new Individual[values.size()];
            for(int i=0;i<inds.length;i++){inds[i]=individual("PT");((SimpleFitness)inds[i].fitness).setFitness(s,-((Number)values.get(i)).doubleValue(),false);}
            s.population=new Population();s.population.subpops=new Subpopulation[]{new Subpopulation()};s.population.subpops[0].individuals=inds;
            TournamentSelection selector=new TournamentSelection();field(selector,TournamentSelection.class,"size",num(c.get("size")));selector.probabilityOfPickingSizePlusOne=0;selector.pickWorst=false;
            return map("winner",selector.produce(0,s,0),"random_calls",rng.calls);
        }
        if(kind.equals("node")){
            GPIndividual ind=individual((String)c.get("a"));KozaNodeSelector selector=new KozaNodeSelector();selector.nonterminalProbability=.9;selector.terminalProbability=.1;selector.rootProbability=0;selector.reset();
            GPNode selected=selector.pickNode(s,0,0,ind,ind.trees[0]);List<GPNode> nodes=new ArrayList<>();walk(ind.trees[0].child,nodes);
            int index=0;while(nodes.get(index)!=selected)index++;return map("index",index,"random_calls",rng.calls);
        }
        if(kind.equals("cross")){
            GPIndividual a=individual((String)c.get("a")),b=individual((String)c.get("b"));Cross pipe=new Cross();pipe.parents();pipe.likelihood=1;pipe.tree1=pipe.tree2=0;pipe.numTries=num(c.getOrDefault("attempts",1));pipe.maxDepth=num(c.getOrDefault("max_height",7))+1;pipe.maxSize=num(c.getOrDefault("max_nodes",255));pipe.tossSecondParent=false;
            pipe.nodeselect1=new FixedSelector((List)c.get("positions_a"));pipe.nodeselect2=new FixedSelector((List)c.get("positions_b"));FixedSource source=new FixedSource(a,b);pipe.sources=new BreedingSource[]{source,source};Individual[] out=new Individual[2];int n=pipe.produce(1,num(c.get("outputs")),0,0,out,s,0);
            List<String> children=new ArrayList<>();for(int i=0;i<n;i++)children.add(expression(((GPIndividual)out[i]).trees[0].child));
            return map("children",children,"parents",List.of(expression(a.trees[0].child),expression(b.trees[0].child)),"outputs",n);
        }
        if(kind.equals("mutation")){
            GPIndividual a=individual((String)c.get("a"));MutationPipeline pipe=new MutationPipeline();pipe.tree=0;pipe.likelihood=1;pipe.numTries=1;field(pipe,MutationPipeline.class,"maxDepth",num(c.getOrDefault("max_height",7))+1);pipe.maxSize=num(c.getOrDefault("max_nodes",255));pipe.nodeselect=new FixedSelector(List.of(c.get("position")));pipe.builder=new FixedBuilder((String)c.get("subtree"));pipe.sources=new BreedingSource[]{new FixedSource(a)};Individual[] out=new Individual[1];pipe.produce(1,1,0,0,out,s,0);
            return map("children",List.of(expression(((GPIndividual)out[0]).trees[0].child)),"parents",List.of(expression(a.trees[0].child)));
        }
        if(kind.equals("elite")){
            GPIndividual a=individual("PT"),b=individual("UT"),d=individual("DT");
            ((SimpleFitness)a.fitness).setFitness(s,-2,false);((SimpleFitness)b.fitness).setFitness(s,-1,false);((SimpleFitness)d.fitness).setFitness(s,-3,false);a.evaluated=b.evaluated=d.evaluated=true;
            s.population=new Population();s.population.subpops=new Subpopulation[]{new Subpopulation()};s.population.subpops[0].individuals=new Individual[]{a,b,d};
            Population next=new Population();next.subpops=new Subpopulation[]{new Subpopulation()};next.subpops[0].individuals=new Individual[3];new EliteBreeder().load(s,next);
            GPIndividual elite=(GPIndividual)next.subpops[0].individuals[2];
            return map("expression",expression(elite.trees[0].child),"position",2,"evaluated",elite.evaluated,"independent",elite!=b&&elite.trees[0].child!=b.trees[0].child);
        }
        if(kind.equals("last_generation")){
            s.generation=3;s.numGenerations=4;s.statistics=new Statistics();s.statistics.children=new Statistics[0];ObservedEvaluator eval=new ObservedEvaluator();s.evaluator=eval;
            // breeder/exchanger/problem intentionally absent: any access would fail.
            int code=s.evolve();return map("evaluated_last_population",eval.calls==1,"evaluated_generations",s.generation,"no_breeding_or_rotation",code==EvolutionState.R_FAILURE);
        }
        if(kind.equals("multi")){
            MultiBreedingPipeline pipe=new MultiBreedingPipeline();pipe.generateMax=false;pipe.sources=new BreedingSource[]{new CountSource("crossover",2,.8),new CountSource("mutation",1,.95),new CountSource("reproduction",1,1.)};
            return map("outputs",pipe.produce(1,num(c.get("capacity")),0,0,new Individual[2],s,0),"random_calls",rng.calls);
        }
        throw new IllegalArgumentException("unknown case "+kind);
    }
    public static void main(String[] args)throws Exception{
        Map input=m(Json.parse(Files.readString(Path.of(args[0]))));List<Object> rows=new ArrayList<>();for(Object value:(List)input.get("cases")){Map c=m(value);rows.add(map("case_id",c.get("case_id"),"result",run(c)));}
        Files.writeString(Path.of(args[1]),Json.write(map("cases",rows,"runtime",System.getProperty("java.runtime.version"))));
    }
}
