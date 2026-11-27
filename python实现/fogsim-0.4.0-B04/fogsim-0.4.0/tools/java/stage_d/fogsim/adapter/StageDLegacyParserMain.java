package fogsim.adapter;
import java.nio.file.*;
public final class StageDLegacyParserMain {
 public static void main(String[]a)throws Exception{
  String text=Files.readString(Path.of(a[0]));
  mengxu.rule.evolved.GPRule rule=mengxu.rule.evolved.GPRule.readFromLispExpression(mengxu.rule.RuleType.ROUTING,text);
  Files.writeString(Path.of(a[1]),Json.write(StageDGP.ast(rule.getGPTree().child))+"\n");
 }
}
