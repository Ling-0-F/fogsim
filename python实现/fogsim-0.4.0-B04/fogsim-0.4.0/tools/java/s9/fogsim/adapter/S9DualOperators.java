package fogsim.adapter;

import ec.*;
import ec.gp.*;
import ec.gp.koza.*;
import ec.util.*;
import mengxu.gp.GPRuleEvolutionState;
import mengxu.algorithm.multipletreegp.AllIndexAllSwapCrossoverPipeline;
import java.nio.file.*;
import java.util.*;

/** B03 observations delegate to the original Java operators without overlays. */
public class S9DualOperators extends S9Operators {
    static final String[] ROLES={"sequencing","routing"};
    static GPRuleEvolutionState dualState(Controlled rng){
        GPRuleEvolutionState s=state(rng);GPInitializer init=(GPInitializer)s.initializer;
        GPTreeConstraints second=new GPTreeConstraints();second.treetype=init.types[0];second.functionset=init.treeConstraints[0].functionset;
        init.treeConstraints=new GPTreeConstraints[]{init.treeConstraints[0],second};
        s.setTerminals(new GPNode[][]{s.getTerminals(0),s.getTerminals(0)});
        return s;
    }
    static GPIndividual dual(List<?> expressions){
        if(expressions.size()!=2)throw new IllegalArgumentException("two roles required");
        GPIndividual ind=new GPIndividual();ind.trees=new GPTree[2];ind.fitness=new ec.simple.SimpleFitness();
        for(int slot=0;slot<2;slot++){
            GPTree tree=individual((String)expressions.get(slot)).trees[0];tree.owner=ind;tree.constraints=(byte)slot;ind.trees[slot]=tree;
        }
        return ind;
    }
    static List<String> genome(GPIndividual ind){return List.of(expression(ind.trees[0].child),expression(ind.trees[1].child));}
    static List<Integer> heights(GPIndividual ind){return List.of(ind.trees[0].child.depth()-1,ind.trees[1].child.depth()-1);}
    static List<Integer> sizes(GPIndividual ind){return List.of(ind.trees[0].child.numNodes(GPNode.NODESEARCH_ALL),ind.trees[1].child.numNodes(GPNode.NODESEARCH_ALL));}
    static boolean disjoint(GPIndividual[] parents,Individual[] children,int n){
        List<Set<GPNode>> groups=new ArrayList<>();
        for(GPIndividual ind:parents){Set<GPNode> set=Collections.newSetFromMap(new IdentityHashMap<>());for(GPTree tree:ind.trees){List<GPNode> list=new ArrayList<>();walk(tree.child,list);for(GPNode node:list)if(!set.add(node))return false;}groups.add(set);}
        for(int i=0;i<n;i++){GPIndividual ind=(GPIndividual)children[i];Set<GPNode> set=Collections.newSetFromMap(new IdentityHashMap<>());for(GPTree tree:ind.trees){List<GPNode> list=new ArrayList<>();walk(tree.child,list);for(GPNode node:list)if(!set.add(node))return false;}groups.add(set);}
        for(int i=0;i<groups.size();i++)for(int j=i+1;j<groups.size();j++)for(GPNode node:groups.get(i))if(groups.get(j).contains(node))return false;
        return true;
    }
    static class ObservedCross extends AllIndexAllSwapCrossoverPipeline {
        List<Boolean> legality=new ArrayList<>();
        void initializeParents(){parents=new GPIndividual[2];}
        @Override public boolean verifyPoints(GPInitializer init,GPNode donor,GPNode recipient){boolean ok=super.verifyPoints(init,donor,recipient);legality.add(ok);return ok;}
    }
    static class ObservedMutation extends MutationPipeline {
        List<Boolean> legality=new ArrayList<>();
        @Override public boolean verifyPoints(GPNode donor,GPNode recipient){boolean ok=super.verifyPoints(donor,recipient);legality.add(ok);return ok;}
    }
    static class SubtreeSequence extends GPNodeBuilder {
        List<?> trees;int at;
        SubtreeSequence(List<?> input){trees=input;}
        public Parameter defaultBase(){return new Parameter("controlled");}
        public GPNode newRootedTree(EvolutionState s,GPType t,int th,GPNodeParent parent,GPFunctionSet fs,int arg,int size){
            GPNode tree=individual((String)trees.get(at++)).trees[0].child;tree.parent=parent;tree.argposition=(byte)arg;return tree;
        }
    }
    static Object execute(Map c){
        String kind=(String)c.get("kind");Controlled rng=new Controlled((List)c.getOrDefault("ints",List.of()),(List)c.getOrDefault("reals",List.of()));
        GPRuleEvolutionState state=dualState(rng);GPInitializer init=(GPInitializer)state.initializer;
        if(kind.equals("initialize")){
            List<Object> out=new ArrayList<>();
            for(int slot=0;slot<2;slot++){
                Map spec=m(((List)c.get("trees")).get(slot));HalfBuilder builder=new HalfBuilder();builder.minDepth=builder.maxDepth=num(spec.get("height"))+1;builder.pickGrowProbability=spec.get("method").equals("grow")?1:0;
                GPNode tree=builder.newRootedTree(state,init.types[0],0,new GPTree(),init.treeConstraints[slot].functionset,0,-1);
                out.add(map("role",ROLES[slot],"expression",expression(tree),"height",tree.depth()-1,"nodes",tree.numNodes(GPNode.NODESEARCH_ALL)));
            }
            return map("trees",out,"random_calls",rng.calls);
        }
        GPIndividual a=dual((List)c.get("a"));List<String> beforeA=genome(a);int slot=num(c.get("slot"));
        if(kind.equals("cross")){
            GPIndividual b=dual((List)c.get("b"));List<String> beforeB=genome(b);
            ObservedCross pipe=new ObservedCross();pipe.initializeParents();pipe.likelihood=1;pipe.numTries=num(c.get("attempts"));
            pipe.tree1=pipe.tree2=Boolean.TRUE.equals(c.get("unfixed"))?CrossoverPipeline.TREE_UNFIXED:slot;
            pipe.maxDepth=num(c.getOrDefault("max_height",7))+1;pipe.maxSize=num(c.getOrDefault("max_nodes",255));pipe.tossSecondParent=false;
            FixedSelector first=new FixedSelector((List)c.get("positions_a")),second=new FixedSelector((List)c.get("positions_b"));pipe.nodeselect1=first;pipe.nodeselect2=second;
            FixedSource source=new FixedSource(a,b);pipe.sources=new BreedingSource[]{source,source};Individual[] out=new Individual[2];
            int n=pipe.produce(1,num(c.get("outputs")),0,0,out,state,0);
            List<Object> children=new ArrayList<>();for(int i=0;i<n;i++)children.add(map("expressions",genome((GPIndividual)out[i]),"heights",heights((GPIndividual)out[i]),"nodes",sizes((GPIndividual)out[i])));
            List<Object> history=new ArrayList<>();int directions=n==1?1:2;for(int i=0;i<pipe.legality.size();i+=directions)history.add(new ArrayList<>(pipe.legality.subList(i,i+directions)));
            return map("children",children,"legal_history",history,"attempts",first.at,"parents_unchanged",genome(a).equals(beforeA)&&genome(b).equals(beforeB),"disjoint",disjoint(new GPIndividual[]{a,b},out,n),"random_calls",rng.calls);
        }
        if(kind.equals("mutation")){
            ObservedMutation pipe=new ObservedMutation();pipe.tree=MutationPipeline.TREE_UNFIXED;pipe.likelihood=1;pipe.numTries=num(c.get("attempts"));
            field(pipe,MutationPipeline.class,"maxDepth",num(c.getOrDefault("max_height",7))+1);pipe.maxSize=num(c.getOrDefault("max_nodes",255));
            pipe.nodeselect=new FixedSelector((List)c.get("positions"));pipe.builder=new SubtreeSequence((List)c.get("subtrees"));pipe.sources=new BreedingSource[]{new FixedSource(a)};
            Individual[] out=new Individual[1];pipe.produce(1,1,0,0,out,state,0);GPIndividual child=(GPIndividual)out[0];
            return map("children",List.of(map("expressions",genome(child),"heights",heights(child),"nodes",sizes(child))),"legal_history",pipe.legality,"attempts",pipe.legality.size(),"parents_unchanged",genome(a).equals(beforeA),"disjoint",disjoint(new GPIndividual[]{a},out,1),"random_calls",rng.calls);
        }
        throw new IllegalArgumentException("unknown case "+kind);
    }
    public static void main(String[] args)throws Exception{
        Map input=m(Json.parse(Files.readString(Path.of(args[0]))));List<Object> rows=new ArrayList<>();for(Object value:(List)input.get("cases")){Map c=m(value);rows.add(map("case_id",c.get("case_id"),"result",execute(c)));}
        Files.writeString(Path.of(args[1]),Json.write(map("cases",rows,"runtime",System.getProperty("java.runtime.version"))));
    }
}
