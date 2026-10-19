/** Check document boundaries without mistaking comments or raw-text for tags. */
export function documentStructureErrors(source) {
 const tokens=/<!--[\s\S]*?-->|<(script|style|title|textarea|iframe)\b[^>]*>[\s\S]*?<\/\1\s*>|<\/?(?:html|head|body)\b[^>]*>/gi;
 const actual=[...source.matchAll(tokens)].map(m=>m[0]).filter(t=>/^<\/?(?:html|head|body)\b/i.test(t)).map(t=>t.match(/^<\/?\w+/)[0].toLowerCase());
 const expected=['<html','<head','</head','<body','</body','</html'];
 const errors=JSON.stringify(actual)===JSON.stringify(expected)?[]:['invalid or nested document boundaries: '+actual.join(' ')];
 // These containers require explicit end tags; unlike p/li, they cannot be
 // implicitly closed. Ignore script literals and comments while balancing.
 const containers=/<!--[\s\S]*?-->|<(script|style|title|textarea|iframe)\b[^>]*>[\s\S]*?<\/\1\s*>|<\/?(?:div|section|article|main|nav|aside|header|footer|figure|form|table)\b[^>]*>/gi;
 const stack=[];
 for(const match of source.matchAll(containers)) {
  const tag=match[0].match(/^<(\/)?(div|section|article|main|nav|aside|header|footer|figure|form|table)\b/i);
  if(!tag)continue;
  const name=tag[2].toLowerCase();
  if(!tag[1])stack.push(name);
  else if(stack.at(-1)===name)stack.pop();
  else errors.push('unexpected container end tag: '+name+'; open: '+stack.join(' > '));
 }
 if(stack.length)errors.push('unclosed containers: '+stack.join(' > '));
 return errors;
}
