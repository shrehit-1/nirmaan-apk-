"""
NIRMAAN - AI Market Pricing Service
Uses Gemini with real-time Google Search grounding to research CURRENT
market prices of similar handmade products, instead of relying on a
static local database. This is the "primary" market pricing path; the
existing local comparable-engine (market_data_service) becomes the
offline/alternate fallback when this isn't available (no key, no
internet, or the search-grounded call fails).
"""
import os
import re
import json
from typing import Optional, Dict, Any, List

from ..config import GEMINI_API_KEY, GEMINI_TEXT_MODEL

PROMPT_TEMPLATE = """You are a pricing research assistant for Indian handmade/artisan products.

Use Google Search to find CURRENT, real listings for products similar to:
- Product: {product_name}
- Category: {category}
- Material: {material}
- Craft technique: {craft_type}
- Handmade: {is_handmade}

Search sites like Amazon.in, Etsy, Flipkart, Meesho, IndiaMART, and
artisan marketplaces. Focus specifically on HANDMADE/handcrafted items —
never compare against mass-manufactured/factory versions of a similar-
looking product, since handmade work commands a fair premium for labour
and skill.

Based on what you actually find, respond with STRICT JSON only (no
markdown fences, no commentary) matching this exact schema:
{{
  "estimated_min_price": <integer, INR>,
  "estimated_max_price": <integer, INR>,
  "typical_market_price": <integer, INR>,
  "confidence_badge_text": "<short label e.g. 'High Confidence' / 'Moderate Confidence' / 'Limited Data'>",
  "online_presence": "<one short sentence on how common this product category is online>",
  "reasoning": "<2-3 sentences explaining the price range based on what you found, mentioning real price points if possible>",
  "comparables": [
    {{"title": "<product title found>", "price": <integer INR>, "seller": "<platform/seller name>", "source": "<domain, e.g. amazon.in>"}}
  ]
}}

If you genuinely cannot find enough real listings to be confident, set
confidence_badge_text to "Limited Data" and say so honestly in
"reasoning" rather than inventing precise numbers. Include at most 5
comparables, only ones you actually found evidence for."""


class AIMarketPricingService:
    def __init__(self):
        self._client = None
        self.last_error: Optional[str] = None

    def _get_api_key(self) -> str:
        return (os.getenv("GEMINI_API_KEY", "").strip() or
                os.getenv("GOOGLE_API_KEY", "").strip() or
                GEMINI_API_KEY).strip()

    def is_available(self) -> bool:
        key = self._get_api_key()
        return bool(key and len(key) > 5)

    def _get_client(self):
        if not self.is_available():
            return None
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self._get_api_key(), vertexai=False)
            except Exception as e:
                print(f"[AIMarketPricingService] Could not initialize Google GenAI client: {e}")
                return None
        return self._client

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    @staticmethod
    def _extract_json_object(text: str) -> Optional[str]:
        """Search-grounded responses sometimes include a sentence or two
        before/after the JSON; pull out the first {...} block."""
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start:end + 1]

    def research_live_market_price(
        self,
        product_name: str,
        category: str = "Handicrafts",
        material: str = "Natural Material",
        craft_type: str = "Handmade",
        is_handmade: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Returns a dict with estimated price range, reasoning, comparables,
        and real cited `sources` (extracted from Gemini's actual Google
        Search grounding metadata, not hallucinated), or None if this
        live-search path isn't available/fails — caller should fall back
        to the offline comparable-engine (market_data_service).
        """
        self.last_error = None
        client = self._get_client()
        if not client:
            self.last_error = "Gemini API key is not configured on the server."
            return None

        try:
            from google.genai import types

            model = os.getenv("GEMINI_TEXT_MODEL", GEMINI_TEXT_MODEL or "gemini-3.6-flash").strip()
            prompt = PROMPT_TEMPLATE.format(
                product_name=product_name,
                category=category,
                material=material,
                craft_type=craft_type,
                is_handmade="Yes" if is_handmade else "No"
            )

            response = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )

            raw_text = getattr(response, "text", None)
            if not raw_text:
                self.last_error = "Gemini returned an empty response."
                return None

            cleaned = self._strip_code_fence(raw_text)
            json_str = self._extract_json_object(cleaned) or cleaned
            data = json.loads(json_str)

            # Pull the REAL sources Gemini actually grounded its answer in,
            # straight from the search grounding metadata (not model text),
            # so what we show the artisan is genuinely verifiable.
            sources: List[Dict[str, str]] = []
            try:
                candidate = response.candidates[0]
                grounding = getattr(candidate, "grounding_metadata", None)
                chunks = getattr(grounding, "grounding_chunks", None) or []
                for chunk in chunks[:6]:
                    web = getattr(chunk, "web", None)
                    if web and getattr(web, "uri", None):
                        sources.append({
                            "title": getattr(web, "title", "") or web.uri,
                            "url": web.uri
                        })
            except Exception as e:
                print(f"[AIMarketPricingService] Could not extract grounding sources: {e}")

            return {
                "estimated_min_price": int(data.get("estimated_min_price", 0)),
                "estimated_max_price": int(data.get("estimated_max_price", 0)),
                "typical_market_price": int(data.get("typical_market_price", 0)),
                "confidence_badge_text": data.get("confidence_badge_text", "Moderate Confidence"),
                "online_presence": data.get("online_presence", ""),
                "reasoning": data.get("reasoning", ""),
                "comparables": data.get("comparables", [])[:5],
                "sources": sources,
                "provider": "gemini_live_search"
            }

        except json.JSONDecodeError as e:
            self.last_error = f"Could not parse Gemini's response as JSON: {e}"
            return None
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            print(f"[AIMarketPricingService] Live market research failed: {self.last_error}")
            return None


ai_market_pricing_service = AIMarketPricingService()
