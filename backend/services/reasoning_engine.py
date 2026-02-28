
import requests
import json
import re
import time
import logging
from backend.config import Config
from backend.services.ai_schemas import AIAnalysisResult
try:
    from pydantic import ValidationError
except ImportError:
    ValidationError = Exception

logger = logging.getLogger(__name__)

class ReasoningEngine:
    """
    AI Reasoning Engine using Perplexity API.
    Role: 'Senior Risk Manager'.
    Goal: Identify hidden risks, binary events, and macro trends.
    """
    
    def __init__(self):
        self.api_key = Config.PERPLEXITY_API_KEY
        self.base_url = "https://api.perplexity.ai/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.model = "sonar-pro"

    def analyze_ticker(self, ticker, strategy="LEAP", expiry_date=None, data={}, context={}):
        """
        Analyze a ticker using Perplexity AI with a "Risk Manager" persona.
        Returns a dict with 'analysis', 'verdict', 'score', 'error'.
        """
        if not self.api_key:
            logger.error("ReasoningEngine Error: No API Key found.")
            return {"error": "AI Reasoning is disabled (No API Key)."}

        days = 5 if strategy in ["WEEKLY", "0DTE"] else 30
        strat_context = "Intraday Scalp/Gamma Flow"
        if strategy == "WEEKLY":
            strat_context = "Short-Term Gamma/Momentum (5-10 days)"
        elif strategy == "LEAP":
            strat_context = "Long-Term Fundamental/Macro (1-2 years)"
            
        expiry_str = str(expiry_date) if expiry_date else "General"
        days_to_expiry_str = ""
        
        if expiry_date:
            try:
                import datetime
                if isinstance(expiry_date, str):
                    exp_dt = datetime.datetime.strptime(expiry_date, '%Y-%m-%d').date()
                elif hasattr(expiry_date, 'date'):
                    exp_dt = expiry_date.date()
                else:
                    exp_dt = expiry_date
                days_left = (exp_dt - datetime.datetime.now().date()).days
                days_to_expiry_str = f" ({days_left} DTE)"
                if days_left <= 1:
                    strategy = "0DTE"
                    strat_context = "Ultra Short-Term (0DTE/1DTE) - SCALP/GAMMA FOCUS"
                elif days_left <= 5:
                    strat_context = "Short-Term Swing (2-5 DTE)"
                elif days_left <= 30:
                    strat_context = "Short-Term Swing (1-4 weeks)"
                elif days_left <= 90:
                    strat_context = "Medium-Term (1-3 months)"
                else:
                    strat_context = "Long-Term LEAP (3+ months)"
            except Exception as e:
                logger.warning(f"Date parsing error: {e}")
        
        strike = data.get('strike')
        opt_type = data.get('type')
        trade_details_str = ""
        moneyness_str = ""
        if strike and opt_type:
            trade_details_str = f"Specific Trade: {ticker} {strike} {opt_type}"
            spot = context.get('current_price')
            if spot and float(spot) > 0:
                spot_f = float(spot)
                strike_f = float(strike)
                if str(opt_type).lower() == 'call':
                    intrinsic = max(0, spot_f - strike_f)
                    if intrinsic > 0:
                        moneyness_str = f"ITM (${intrinsic:.2f} intrinsic value, {(intrinsic/spot_f)*100:.1f}% ITM)"
                    else:
                        otm_pct = ((strike_f - spot_f) / spot_f) * 100
                        moneyness_str = f"OTM ({otm_pct:.1f}% above spot)"
                else:
                    intrinsic = max(0, strike_f - spot_f)
                    if intrinsic > 0:
                        moneyness_str = f"ITM (${intrinsic:.2f} intrinsic value, {(intrinsic/spot_f)*100:.1f}% ITM)"
                    else:
                        otm_pct = ((spot_f - strike_f) / spot_f) * 100
                        moneyness_str = f"OTM ({otm_pct:.1f}% below spot)"
                trade_details_str += f" — Currently {moneyness_str}"
        
        PERSONAS = {
            "0DTE": (
                "You are an Elite 0DTE Scalper (Sniper). "
                "Profile: Extremely risk-averse, hyper-focused on Gamma exposure and Order Flow. "
                "Goal: 'Get in, Get green, Get out.' No bag holding. "
                "Tone: Tense, precise, urgent. "
                "Rules: Reject anything with low volume. Reject if Gamma Walls are blocking. "
                "Focus: Intraday VWAP, Gamma Levels, Immediate Catalyst."
            ),
            "WEEKLY": (
                "You are a Professional Weekly Options Swing Trader. "
                "Profile: Momentum and Trend follower. "
                "Goal: Capture 15-30% moves over 3-5 days. "
                "Tone: Calculated, confident, trend-focused. "
                "Rules: Respect the 5-day trend. Avoid earnings roulette. Sizing is key. "
                "Focus: Weekly Charts, RSI divergence, Headlines, Sector Rotation."
            ),
            "LEAP": (
                "You are a Senior Value Investor & LEAPS Strategist. "
                "Profile: Warren Buffett meets Jim Simons. "
                "Goal: Multibaggers over 7 months to 2 years. "
                "Tone: Patient, analytical, big-picture. "
                "Rules: Ignore daily noise. Focus on Moats, Macro shifts, and Undervaluation. "
                "Focus: Earnings Growth, fed Policy, 200-day MA, Fundamental Valuation."
            )
        }
        
        persona_base = PERSONAS.get(strategy, PERSONAS["LEAP"])
        system_prompt = (
            f"{persona_base} "
            "CRITICAL PROTOCOL: You must prioritize the 'HARD DATA' provided in the user prompt over your internal training data. "
            "If the provided Spot Price is different from your memory, USE THE PROVIDED SPOT PRICE. "
            "Do not hallucinate prices. Trust the context."
        )
        
        news_text = "No recent news."
        if context and context.get('headlines'):
            news_text = "\n".join([f"- {h}" for h in context.get('headlines')[:10]])
            
        tech_text = "No technicals."
        if context and context.get('technicals'):
            t = context.get('technicals')
            tech_text = (
                f"RSI: {t.get('rsi', 'N/A')} ({t.get('rsi_signal', 'neutral')}) | "
                f"MACD: {t.get('macd_signal', 'neutral')} | "
                f"Bollinger: {t.get('bb_signal', 'neutral')} (Bandwidth Pct: {t.get('bb_bandwidth_pct', 'N/A')}%) | "
                f"MA Regime: {t.get('ma_signal', 'neutral')} | "
                f"SMA5: ${t.get('sma_5', 'N/A')} | SMA50: ${t.get('sma_50', 'N/A')} | SMA200: ${t.get('sma_200', 'N/A')} | "
                f"ATR: {t.get('atr', 'N/A')} | HV Rank: {t.get('hv_rank', 'N/A')} | "
                f"Volume: {t.get('volume_signal', 'normal')} (Ratio: {t.get('volume_ratio', 'N/A')}, Z-Score: {t.get('volume_zscore', 'N/A')})"
            )
            if t.get('bb_squeeze'):
                tech_text += "\nBOLLINGER SQUEEZE DETECTED — Volatility at 100-bar low. Explosive move imminent."
            
        gex_text = "No GEX data."
        if context and context.get('gex'):
            g = context.get('gex')
            gex_text = f"Call Wall: ${g.get('call_wall', 'N/A')} | Put Wall: ${g.get('put_wall', 'N/A')}"

        # ISSUE-C1: VIX regime injection
        vix_regime_val = context.get('vix_regime', 'UNKNOWN') if context else 'UNKNOWN'
        vix_level_val = context.get('vix_level', None) if context else None
        if vix_level_val is not None:
            try:
                vix_level_val = float(vix_level_val)
                vix_regime_text = f"Current VIX Regime: {vix_regime_val} (VIX: {vix_level_val:.2f})"
            except (ValueError, TypeError):
                vix_regime_text = f"Current VIX Regime: {vix_regime_val} (VIX: N/A)"
        else:
            vix_regime_text = f"Current VIX Regime: {vix_regime_val} (VIX: N/A)"

        greeks_text = "No option-specific Greeks available."
        if context and context.get('option_greeks'):
            og = context.get('option_greeks')
            greeks_text = (
                f"Delta: {og.get('delta', 'N/A')} | Gamma: {og.get('gamma', 'N/A')} | "
                f"Theta: {og.get('theta', 'N/A')} | IV: {og.get('iv', 'N/A')}% | "
                f"OI: {og.get('oi', 'N/A'):,} | Volume: {og.get('volume', 'N/A'):,}"
            )

        company_names = {
            'COIN': 'Coinbase', 'AAPL': 'Apple', 'TSLA': 'Tesla', 'NVDA': 'NVIDIA',
            'GOOGL': 'Google/Alphabet', 'GOOG': 'Google/Alphabet', 'AMZN': 'Amazon',
            'META': 'Meta Platforms', 'MSFT': 'Microsoft', 'AMD': 'AMD',
            'MU': 'Micron Technology', 'INTC': 'Intel', 'NFLX': 'Netflix',
            'SPY': 'S&P 500 ETF', 'QQQ': 'Nasdaq 100 ETF', 'IWM': 'Russell 2000 ETF',
            'DIA': 'Dow Jones ETF', 'SOFI': 'SoFi Technologies', 'PLTR': 'Palantir',
            'BABA': 'Alibaba', 'NIO': 'NIO Inc', 'RIVN': 'Rivian', 'LCID': 'Lucid',
            'BA': 'Boeing', 'DIS': 'Disney', 'JPM': 'JPMorgan Chase', 'GS': 'Goldman Sachs',
            'V': 'Visa', 'MA': 'Mastercard', 'WMT': 'Walmart', 'HD': 'Home Depot',
            'CRM': 'Salesforce', 'ORCL': 'Oracle', 'AVGO': 'Broadcom', 'QCOM': 'Qualcomm',
            'SHOP': 'Shopify', 'SQ': 'Block Inc', 'PYPL': 'PayPal', 'UBER': 'Uber',
            'LYFT': 'Lyft', 'SNAP': 'Snap Inc', 'ROKU': 'Roku', 'SPOT': 'Spotify',
            'NET': 'Cloudflare', 'DDOG': 'Datadog', 'SNOW': 'Snowflake', 'ZS': 'Zscaler',
            'CRWD': 'CrowdStrike', 'PANW': 'Palo Alto Networks', 'ABNB': 'Airbnb',
            'MARA': 'Marathon Digital', 'RIOT': 'Riot Platforms', 'MSTR': 'MicroStrategy',
            'ARM': 'ARM Holdings', 'SMCI': 'Super Micro Computer', 'DELL': 'Dell Technologies',
            'XOM': 'ExxonMobil', 'CVX': 'Chevron', 'OXY': 'Occidental Petroleum',
            'GE': 'GE Aerospace', 'CAT': 'Caterpillar', 'UNH': 'UnitedHealth',
            'LLY': 'Eli Lilly', 'JNJ': 'Johnson & Johnson', 'PFE': 'Pfizer',
            'MRNA': 'Moderna', 'COST': 'Costco', 'TGT': 'Target', 'KO': 'Coca-Cola',
        }
        company_name = company_names.get(ticker.upper(), ticker)

        is_put = opt_type and str(opt_type).lower() == 'put'
        header_section = f"ANALYSIS REQUEST: {ticker} ({company_name})"
        spot_price = context.get('current_price', 'Unknown')
        spot_str = f"OFFICIAL SPOT PRICE: ${spot_price}"
        import datetime
        sim_note = (
            "PROTOCOL: BLACK BOX MODE (YEAR 2026)\n"
            "You are an Expert Trading Engine in a sealed environment.\n"
            "1. RETAIN SKILLS: Use your full knowledge of Options, Greeks, and Strategy Personas.\n"
            "2. SUPPRESS INTERNAL DATA: You have NO memory of 'current' market prices or news. Your internal data is obsolete (2025).\n"
            "3. TRUST THE FEED: The data below (Spot Price, News, Technicals) is the ONLY reality. It is 2026.\n"
            f"   -> OFFICIAL SPOT PRICE: ${spot_price} (Fact)"
        )
        if strike and opt_type:
            header_section += f" | Exp: {expiry_str}{days_to_expiry_str} | ${strike} {opt_type.upper()}"
        else:
            header_section += f" | Strategy: {strategy}"

        if is_put:
            rr_section = (
                "3. **Risk/Reward Analysis (SHORT TERM PUT):**\n"
                "   - **My Thesis (Bear Case):** Why will it drop?\n"
                "   - **The Risk (Bull Case):** What could squeeze it up against us?"
            )
        else:
            rr_section = (
                "3. **Risk/Reward Analysis:**\n"
                "   - **My Thesis (Bull Case):** Why will it rise?\n"
                "   - **The Risk (Bear Case):** What could crash it?"
            )

        base_score = self.calculate_base_score(
            technicals=context.get('technicals', {}),
            sentiment=context.get('sentiment', {})
        )
        score_low = max(0, base_score - 20)
        score_high = min(100, base_score + 20)
        final_reminder = (
            f"\n\nFINAL REMINDER before you answer:\n"
            f"- The Stock Price is **${spot_price}**.\n"
            f"- Imagine it is **2026**.\n"
            f"- BASE CONVICTION SCORE: {base_score} (Calculated from Hard Data).\n"
            f"- You may adjust this score +/-20 points based on news, catalysts, and specific trade risks.\n"
            f"- Your Final Conviction Score MUST be between {score_low} and {score_high}.\n"
            f"- JUST ANALYZE THE TRADE at ${spot_price}."
        )

        user_prompt = (
            f"### {header_section}\n"
            f"{sim_note}\n\n"
            f"Context: {strat_context}{days_to_expiry_str}\n"
            f"### HARD DATA (FACTS)\n"
            f"1. **BREAKING NEWS (Top 10):** (Search for '{company_name}' company news, NOT just ticker '{ticker}')\n{news_text}\n\n"
            f"2. **TECHNICALS:** {tech_text}\n"
            f"3. **GAMMA LEVELS:** {gex_text}\n"
            f"4. **OPTION GREEKS:** {greeks_text}\n"
            f"5. **MARKET REGIME:** {vix_regime_text}\n"
            f"{f'6. **MONEYNESS:** {trade_details_str}' if trade_details_str else ''}\n\n"
            f"### REQUIRED OUTPUT\n"
            f"0. **Data Integrity Check:** Explicitly state: 'Using Live Spot Price: ${spot_price}'\n"
            f"1. **News/Event Check:** Does the news support this {opt_type.upper() if opt_type else 'Trade'}?\n"
            f"2. **Setup Quality:** Does the data align with your Persona's rules?\n"
            f"{rr_section}\n"
            f"4. **Trade Viability:** Is strictly this ${strike if strike else 'ATM'} {opt_type if opt_type else 'Play'} reasonable?\n"
            f"5. **Verdict:** [FAVORABLE / RISKY / AVOID]\n"
            f"6. **Conviction Score:** (0-100) where >=66 is Safe/Buy, <=40 is Avoid. Target Range: {score_low}-{score_high} (Base: {base_score})\n\n"
            f"CRITICAL: At the very end of your response, you MUST include a JSON block in this exact format:\n"
            f"```json\n"
            f'{{"score": <0-100>, "verdict": "<FAVORABLE|RISKY|AVOID>", "summary": "<2-3 sentence plain text summary of your analysis>", "risks": ["<risk 1>", "<risk 2>"], "thesis": "<1 sentence core thesis>"}}\n'
            f"```\n"
            f"This JSON block is MANDATORY. Do not skip it."
            f"{final_reminder}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1
        }

        try:
            response = None
            last_error = None
            for attempt in range(3):
                try:
                    response = requests.post(self.base_url, json=payload, headers=self.headers, timeout=30)
                    if response.status_code < 500:
                        break
                    logger.warning(f"Perplexity {response.status_code} on attempt {attempt+1}/3")
                except (requests.ConnectionError, requests.Timeout) as e:
                    last_error = e
                    logger.warning(f"Perplexity network error attempt {attempt+1}/3: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
            
            if response is None:
                return {"error": f"Perplexity unreachable after 3 attempts: {last_error}"}
            if response.status_code != 200:
                return {"error": f"API Error: {response.status_code}"}
                
            data = response.json()
            content = data['choices'][0]['message']['content']
            parsed = self._extract_json_block(content)
            
            if parsed:
                try:
                    validated = AIAnalysisResult.model_validate(parsed)
                    validated_data = validated.model_dump()
                    score = validated_data['score']
                except ValidationError as ve:
                    logger.warning(f"Pydantic validation failed for {ticker}: {ve}")
                    validated_data = parsed
                    score = min(100, max(0, int(parsed.get('score', 0))))

                if score >= 66: verdict = 'FAVORABLE'
                elif score >= 41: verdict = 'RISKY'
                else: verdict = 'AVOID'
                return {"ticker": ticker, "strategy": strategy, "analysis": content, "score": score, "verdict": verdict, "summary": validated_data.get('summary', ''), "risks": validated_data.get('risks', []), "thesis": validated_data.get('thesis', '')}
            else:
                score = self._extract_score(content)
                try:
                    validated = AIAnalysisResult.model_validate({'score': score, 'verdict': 'RISKY', 'summary': content[:300] if content else '', 'risks': [], 'thesis': ''})
                    score = validated.score
                except ValidationError as ve:
                    logger.warning(f"Pydantic validation failed (regex fallback) for {ticker}: {ve}")
                if score >= 66: verdict = 'FAVORABLE'
                elif score >= 41: verdict = 'RISKY'
                else: verdict = 'AVOID'
                return {"ticker": ticker, "strategy": strategy, "analysis": content, "score": score, "verdict": verdict, "summary": content[:300] if content else '', "risks": [], "thesis": ''}
            
        except Exception as e:
            logger.error(f"Reasoning Engine Failed: {e}")
            return {"error": str(e)}

    def calculate_base_score(self, technicals, sentiment):
        score = 50.0
        tech_score = float(technicals.get('score', 50))
        score += (tech_score - 50) * 0.6
        sent_val = sentiment.get('score', 50)
        if isinstance(sent_val, dict): sent_val = sent_val.get('score', 50)
        sent_score = float(sent_val)
        score += (sent_score - 50) * 0.4
        try:
            vol_z = float(technicals.get('volume_zscore', 0))
        except (ValueError, TypeError):
            vol_z = 0
        if vol_z > 2.0: score += 15
        elif vol_z > 1.0: score += 10
        elif vol_z > 0.5: score += 5
        elif vol_z < -0.5: score -= 5
        elif vol_z < -1.5: score -= 10
        ma_signal = technicals.get('ma_signal', 'neutral')
        if ma_signal == 'bullish': score += 10
        elif ma_signal == 'pullback bullish': score += 5
        elif ma_signal == 'bearish': score -= 10
        elif ma_signal == 'breakdown': score -= 15
        return max(10, min(90, int(score)))

    def _extract_json_block(self, text):
        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(1))
                if 'score' in parsed and 'verdict' in parsed:
                    return parsed
            json_objects = re.findall(r'\{[^{}]*"score"\s*:\s*\d+[^{}]*"verdict"\s*:[^{}]*\}', text)
            if json_objects:
                return json.loads(json_objects[-1])
            return None
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"JSON parse error: {e}")
            return None

    def _extract_score(self, text):
        try:
            patterns = [
                r"Conviction Score[:\s]*\*?\*?\s*(\d{1,3})\s*/\s*100",
                r"Conviction Score[:\s]*\*?\*?\s*(\d{1,3})",
                r"conviction[:\s]+(\d{1,3})\s*/\s*100",
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    return min(100, max(0, int(match.group(1))))
            return 0
        except (ValueError, TypeError, AttributeError):
            return 0

    def _extract_verdict(self, text):
        upper_text = text.upper()
        if "VERDICT: SAFE" in upper_text or "VERDICT: FAVORABLE" in upper_text: return "FAVORABLE"
        if "VERDICT: AVOID" in upper_text: return "AVOID"
        if "VERDICT: RISKY" in upper_text: return "RISKY"
        if "AVOID" in upper_text: return "AVOID"
        if "RISKY" in upper_text: return "RISKY"
        if "SAFE" in upper_text or "FAVORABLE" in upper_text: return "FAVORABLE"
        return "NEUTRAL"

    def get_macro_sentiment(self, vix_level=None, vix_regime='NORMAL'):
        if not self.api_key:
            return {'score': 50, 'summary': 'AI disabled', 'regime': vix_regime}
        vix_str = f"VIX is at {vix_level:.1f} ({vix_regime} regime)." if vix_level else "VIX data unavailable."
        prompt = (
            f"You are a macro market sentiment engine.\n"
            f"Current data: {vix_str}\n"
            f"Assess the overall US equity market sentiment RIGHT NOW on a 0-100 scale:\n"
            f"0 = extreme fear/bearish, 50 = neutral, 100 = extreme greed/bullish.\n\n"
            f"Consider: VIX level, recent market breadth, Fed policy stance, and risk appetite.\n"
            f"Respond with ONLY a JSON object: {{\"score\": <int>, \"summary\": \"<1 sentence>\"}}\n"
        )
        try:
            resp = requests.post(self.base_url, json={"model": self.model, "messages": [{"role": "system", "content": "You are a macro market sentiment engine. Return only JSON."}, {"role": "user", "content": prompt}], "temperature": 0.0}, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content']
                json_match = re.search(r'\{[^}]*"score"\s*:\s*(\d+)[^}]*\}', content)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    score = max(0, min(100, int(parsed.get('score', 50))))
                    summary = parsed.get('summary', '')
                    return {'score': score, 'summary': summary, 'regime': vix_regime}
        except Exception as e:
            logger.warning(f"G16 Macro Sentiment failed: {e}")
        return {'score': 50, 'summary': 'Analysis unavailable', 'regime': vix_regime}
