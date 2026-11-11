"""Conservative handling of explicit resolutions in company headlines."""

import re


_RESOLVED = re.compile(
    r"\b(?:avoids|avoided|averts|averted) delisting\b"
    r"|\b(?:withdraws|withdrew|rescinds|rescinded) (?:its |the )?delisting notice\b"
    r"|\bdelisting (?:notice|proceedings) (?:was |were |has been |have been )?(?:withdrawn|rescinded|cancelled|canceled)\b"
    r"|\b(?:regains|regained) (?:(?:nasdaq|nyse) )?(?:listing )?compliance (?:after|following) (?:receiving )?(?:a |the )?delisting (?:notice|warning)\b"
    r"|\b(?:investigation|sec inquiry) (?:was |has been )?closed without (?:enforcement )?action\b"
    r"|\blawsuit (?:was |has been )?dismissed with prejudice\b"
)
_UNCERTAIN = re.compile(
    r"\b(?:if|unless|could|may|might|would|not|never|pending|temporarily|for now|fails? to|failed to|remains? at risk)\b|\?"
)


def unresolved_news_text(headlines):
    """Remove only an explicit resolution phrase, never a different risk mention."""
    cleaned = []
    for headline in headlines or ():
        text = " ".join(str(headline).lower().split())
        if not _UNCERTAIN.search(text):
            text = _RESOLVED.sub(" ", text)
        cleaned.append(text)
    return " ".join(cleaned)
