export const captionText = value => String(value || "").normalize("NFC")
  .replace(/[\u200b-\u200d\ufeff]/g, "").replace(/\s+/g, " ").trim();

export function auditCaption(snapshot, title, expectedTags) {
  const text = captionText(snapshot?.text);
  const pattern = /#[\p{L}\p{M}\p{N}_]+/gu;
  const actualTags = text.match(pattern) || [];
  const remaining = [...actualTags];
  const missing = [];
  for (const tag of expectedTags.map(captionText)) {
    const index = remaining.indexOf(tag);
    if (index < 0) missing.push(tag);
    else remaining.splice(index, 1);
  }
  const actualTitle = captionText(text.replace(pattern, " "));
  return { present: !!snapshot?.present, actualTitle, actualTags, missing, extra: remaining,
    titleMatches: actualTitle === captionText(title),
    tagsMatch: !missing.length && !remaining.length };
}
