package fogsim.adapter;

import java.util.*;

/** Small strict JSON codec for the fixed input/output boundary; no scheduling code. */
final class Json {
    private final String text;
    private int at;
    private Json(String text) { this.text = text; }

    static Object parse(String text) {
        Json p = new Json(text);
        Object value = p.value();
        p.space();
        if (p.at != text.length()) throw p.error("trailing data");
        return value;
    }

    private IllegalArgumentException error(String reason) {
        return new IllegalArgumentException("JSON at " + at + ": " + reason);
    }

    private void space() {
        while (at < text.length() && " \t\r\n".indexOf(text.charAt(at)) >= 0) at++;
    }

    private boolean take(char c) {
        space();
        if (at < text.length() && text.charAt(at) == c) { at++; return true; }
        return false;
    }

    private Object value() {
        space();
        if (at == text.length()) throw error("missing value");
        char c = text.charAt(at);
        if (c == '"') return string();
        if (take('{')) {
            Map<String,Object> out = new LinkedHashMap<>();
            if (take('}')) return out;
            do {
                space();
                if (at == text.length() || text.charAt(at) != '"') throw error("expected key");
                String key = string();
                if (!take(':')) throw error("expected colon");
                if (out.containsKey(key)) throw error("duplicate key " + key);
                out.put(key, value());
            } while (take(','));
            if (!take('}')) throw error("expected closing brace");
            return out;
        }
        if (take('[')) {
            List<Object> out = new ArrayList<>();
            if (take(']')) return out;
            do { out.add(value()); } while (take(','));
            if (!take(']')) throw error("expected closing bracket");
            return out;
        }
        for (String token : List.of("true", "false", "null")) {
            if (text.startsWith(token, at)) {
                at += token.length();
                return token.equals("null") ? null : token.equals("true");
            }
        }
        int start = at;
        while (at < text.length() && "-+0123456789.eE".indexOf(text.charAt(at)) >= 0) at++;
        String token = text.substring(start, at);
        if (!token.matches("-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?")) throw error("invalid number");
        try {
            if (token.indexOf('.') < 0 && token.indexOf('e') < 0 && token.indexOf('E') < 0)
                return Long.valueOf(token);
            double result = Double.parseDouble(token);
            if (!Double.isFinite(result)) throw error("non-finite number");
            return result;
        } catch (NumberFormatException ex) { throw error("number out of range"); }
    }

    private String string() {
        at++;
        StringBuilder out = new StringBuilder();
        while (at < text.length()) {
            char c = text.charAt(at++);
            if (c == '"') return out.toString();
            if (c < 32) throw error("unescaped control character");
            if (c != '\\') { out.append(c); continue; }
            if (at == text.length()) throw error("unfinished escape");
            c = text.charAt(at++);
            switch (c) {
                case '"': case '\\': case '/': out.append(c); break;
                case 'b': out.append('\b'); break;
                case 'f': out.append('\f'); break;
                case 'n': out.append('\n'); break;
                case 'r': out.append('\r'); break;
                case 't': out.append('\t'); break;
                case 'u':
                    if (at + 4 > text.length()) throw error("short Unicode escape");
                    try { out.append((char) Integer.parseInt(text.substring(at, at + 4), 16)); }
                    catch (NumberFormatException ex) { throw error("invalid Unicode escape"); }
                    at += 4; break;
                default: throw error("invalid escape");
            }
        }
        throw error("unterminated string");
    }

    static String write(Object value) {
        if (value == null) return "null";
        if (value instanceof String) {
            StringBuilder out = new StringBuilder("\"");
            for (char c : ((String) value).toCharArray()) {
                switch (c) {
                    case '"': out.append("\\\""); break;
                    case '\\': out.append("\\\\"); break;
                    case '\n': out.append("\\n"); break;
                    case '\r': out.append("\\r"); break;
                    case '\t': out.append("\\t"); break;
                    default:
                        if (c < 32 || Character.isSurrogate(c)) out.append(String.format("\\u%04x", (int) c));
                        else out.append(c);
                }
            }
            return out.append('"').toString();
        }
        if (value instanceof Boolean || value instanceof Number) {
            if (value instanceof Double && !Double.isFinite((Double) value))
                throw new IllegalArgumentException("cannot serialize non-finite double");
            return value.toString();
        }
        if (value instanceof Map) {
            StringJoiner out = new StringJoiner(",", "{", "}");
            for (Map.Entry<?,?> entry : ((Map<?,?>) value).entrySet())
                out.add(write(entry.getKey().toString()) + ":" + write(entry.getValue()));
            return out.toString();
        }
        if (value instanceof Collection) {
            StringJoiner out = new StringJoiner(",", "[", "]");
            for (Object entry : (Collection<?>) value) out.add(write(entry));
            return out.toString();
        }
        throw new IllegalArgumentException("unsupported JSON object " + value.getClass());
    }
}
