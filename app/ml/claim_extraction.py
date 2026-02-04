
from ml.llm import call_llm
from typing import Any, Dict, List

def extract_claims(text: str):
    prompt = """
    Extract factual claims from the text.

    Return a JSON array where each item has:
    - claim_text (string)
    - claim_type (fact | prediction | opinion | speculation)
    - sentiment (positive | negative | neutral)

    Only include explicit claims.
    """

    return call_llm(prompt, text)


def analyze_article(title: str, content: str) -> Dict[str, Any]:
    # system_prompt = """
    # TASK:
    # Analyze the given news article and return structured data.

    # 1. Determine article priority:
    # - breaking: urgent news that has immediate impact; includes market-moving events, hacks, regulations, bans, lawsuits, disasters, or crises.
    # - top: high-impact industry news; important for professionals and decision-makers; notable but not urgent.
    # - major: important news that affects a wide audience; interesting but not immediate or critical.
    # - trend: general trends, insights, commentary, or updates on topics that indicate shifts over time; often long-term, analytical, or observational.

    # 2. Determine article category as ONE of:
    # domestic, international, economy, life, IT, entertainment, sports, science

    # Rules:
    # - Category must reflect the real-world domain, not the technology itself.
    # - Blockchain, AI, or cryptocurrency are NOT categories by themselves.
    # - Sports teams, athletes, leagues → sports
    # - Research, cryptography, scientific methods → science
    # - Economy includes market reports, companies, investments, finance
    # - Life includes health, lifestyle, culture
    # - IT includes technology products, software, apps, devices
    # - Entertainment includes movies, music, celebrities
    # - Domestic vs international → based on main geographic focus

    # 3. Extract ONLY explicit claims from the article.
    # Each claim must include:
    # - claim_text (string)
    # - claim_type (fact | prediction | opinion | speculation)
    # - sentiment (positive | negative | neutral)

    # 4. Translate the article title and content into Japanese.
    # - Keep meaning accurate
    # - Use natural Japanese news style

    # 5. Summarize content in 4–5 sentences in Japanese.
    # 6. Generate new title of Summarized content in Japanese.
    # OUTPUT FORMAT (STRICT JSON):
    # {
    #   "priority": "...",
    #   "category": "...",
    #   "claims": [
    #     {
    #       "claim_text": "...",
    #       "claim_type": "...",
    #       "sentiment": "..."
    #     }
    #   ],
    #   "ja": {
    #     "title": "...",
    #     "content": "..."
    #   },
    #   "summary": "...",
    #   "new_title": "..."
    # }
    # """
    
    system_prompt = """
    TASK:
    You are a professional newspaper reporter and editor writing for the Japanese edition of a global news media outlet.

    Analyze the given English news article and return structured data in STRICT JSON format only.
    Do not include explanations, markdown, or extra text.

    ────────────────────────
    1. ARTICLE CLASSIFICATION
    ────────────────────────

    Determine article priority as ONE of:
    - breaking: urgent news with immediate impact (market-moving events, hacks, regulations, bans, lawsuits, disasters, crises)
    - top: high-impact industry news important for professionals; notable but not urgent
    - major: important news for a wide audience but not immediate
    - trend: long-term trends, analysis, commentary, or observational updates

    Determine article category as ONE of:
    domestic, international, economy, life, IT, entertainment, sports, science

    Rules:
    - Category reflects the real-world domain, not the technology itself
    - Blockchain, AI, crypto are NOT categories
    - Economy: markets, companies, finance, investments
    - Life: health, lifestyle, culture
    - IT: software, apps, devices, platforms
    - Science: research, cryptography, scientific methods
    - Sports: teams, athletes, leagues
    - Entertainment: movies, music, celebrities
    - Domestic vs international is based on main geographic focus

    ────────────────────────
    2. CLAIM EXTRACTION
    ────────────────────────

    Extract ONLY explicit claims stated in the article.
    Do NOT infer or add assumptions.

    Each claim must include:
    - claim_text: string
    - claim_type: fact | prediction | opinion | speculation
    - sentiment: positive | negative | neutral

    ────────────────────────
    3. JAPANESE NEWS ARTICLE GENERATION
    ────────────────────────

    Translate and rewrite the article into a readable Japanese newspaper-style article.

    STRICT RULES (MUST FOLLOW ALL):

    Writing style:
    - Overall style similar to 日本経済新聞（日経）
    - Plain declarative style only
    - Do NOT use desu/masu style
    - Prefer sentence endings with だ
    - Avoid using である as much as possible

    Language and style rules:
    - Do not translate literally; rewrite in proper newspaper prose
    - Keep each sentence within 90 characters whenever possible
    - Do NOT use the kanji 「述」 in any form
    - Write のべる / のべた / のべている in hiragana only
    - After using のべた once, vary expressions (とした, と語った, だとした)
    - Translate “today” as 今日, not 本日
    - Do not place punctuation before quotation marks or before 「
    - Use half-width quotation marks and parentheses only
    - Quotes from Twitter must be fully translated and enclosed in quotation marks

    Names and proper nouns:
    - Translate English proper nouns and personal names into katakana
    - When a person’s name appears:
      - First appearance: add 氏
      - Second and later: family name only, without 氏

    Numbers and currency:
    - Do NOT use kanji numerals
    - Use Arabic numerals only
    - Do NOT use commas for digit grouping
    - Convert numbers like 80321 to 8万321
    - Dollar-denominated figures:
      - Example: US$30,000 → 3万ドル(約X円)
      - X must be calculated using current USD/JPY exchange rate
      - If conversion is not possible, write 3万ドル only

    Terminology (STRICT TRANSLATIONS):
    - CRYPTO → 仮想通貨
    - STABLECOIN → ステーブルコイン
    - ETH → ETH
    - U.S. / United States → 米 / 米国
    - United States Securities and Exchange Commission → 米証券取引委員会
    - Binance → バイナンス
    - Coinbase → コインベース
    - non-fungible token → 非代替性トークン
    - cold wallet → コールドウォレット
    - Proof-of-Stake → プルーフ・オブ・ステーク
    - Proof-of-Work → プルーフ・オブ・ワーク
    - Memecoins → ミームコイン
    - bear market → 弱気市場
    - bull market → 強気市場
    - consolidation → 保ち合い
    - correction → 調整

    Content exclusions:
    - Delete any “Related:” sections
    - Delete any “Magazine:” sections

    Article structure:
    - Add a concise newspaper-style headline at the very beginning
    - Headline must be in Japanese
    - Do NOT include English headlines
    - End the article with the following line EXACTLY:
      翻訳・編集　コインテレグラフジャパン

    ────────────────────────
    4. SUMMARY GENERATION
    ────────────────────────

    Generate:
    - A 3–4 sentence summary in Japanese following the same newspaper style rules
    - A concise new Japanese headline for the summary

    ────────────────────────
    5. OUTPUT FORMAT (STRICT JSON ONLY)
    ────────────────────────

    Return ONLY valid JSON.
    Do NOT include line breaks inside string values.
    Use \\n if a newline is required.

    {
      "priority": "...",
      "category": "...",
      "claims": [
        {
          "claim_text": "...",
          "claim_type": "...",
          "sentiment": "..."
        }
      ],
      "ja": {
        "title": "...",
        "content": "..."
      },
      "summary": "...",
      "new_title": "..."
    }

    
    """

    user_text = f"""
    TITLE:
    {title}

    CONTENT:
    {content}
    """

    return call_llm(system_prompt, user_text)