
import requests
import json
import re
from backend.config import Config

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
        self.model = "sonar-pro" # High reasoning, online capabilities

    def analyze_ticker(self, ticker, strategy="LEAP", expiry_date=None, data={}, context={}):
        """
        Analyze a ticker using Perplexity AI with a "Risk Manager" persona.
        Returns a dict with 'analysis', 'verdict', 'score', 'error'.
        """
        if not self.api_key:
            print("ReasoningEngine Error: No API Key found.")
            return {"error": "AI Reasoning is disabled (No API Key)."}

        # Contextualize based on strategy
        days = 5 if strategy in ["WEEKLY", "0DTE"] else 30
        
        strat_context = "Intraday Scalp/Gamma Flow"
        if strategy == "WEEKLY":
            strat_context = "Short-Term Gamma/Momentum (5-10 days)"
        elif strategy == "LEAP":
            strat_context = "Long-Term Fundamental/Macro (1-2 years)"
            
        expiry_str = str(expiry_date) if expiry_date else "General"
        days_to_expiry_str = ""
        
        # Calculate days to expiry if provided to give AI proper timeline context
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
                
                # [FIX] Auto-Switch Persona based on Timeframe
                if days_left <= 1:
                    print(f"⚡ 0DTE Detected ({days_left} days). Switching to SNIPER Persona.")
                    strategy = "0DTE" # Force Sniper Persona
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
                print(f"⚠️ Date parsing error: {e}")
        
        # Parse optional specific trade details
        strike = data.get('strike')
        opt_type = data.get('type')
        trade_details_str = ""
        if strike and opt_type:
            trade_details_str = f"Specific Trade: {ticker} {strike} {opt_type}"
        
        # PROMPT ENGINEERING (Refined for V2)
        # PROMPT ENGINEERING (Refined for V2)
        # PERSONA DEFINITIONS
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
        
        # Parse Context (Data Injection) to build user_prompt
        news_text = "No recent news."
        if context and context.get('headlines'):
            news_text = "\n".join([f"- {h}" for h in context.get('headlines')[:10]])
            
        tech_text = "No technicals."
        if context and context.get('technicals'):
            t = context.get('technicals')
            tech_text = (
                f"RSI: {t.get('rsi', 'N/A')} | Trend: {t.get('trend', 'N/A')} | "
                f"Support: {t.get('support', 'N/A')} | Resist: {t.get('resistance', 'N/A')}"
            )
            
        gex_text = "No GEX data."
        if context and context.get('gex'):
            g = context.get('gex')
            gex_text = f"Call Wall: ${g.get('call_wall', 'N/A')} | Put Wall: ${g.get('put_wall', 'N/A')}"

        # DYNAMIC PROMPT CONSTRUCTION (Direction Aware)
        is_put = opt_type and str(opt_type).lower() == 'put'
        
        # Header - FORCE VISIBILITY
        header_section = f"ANALYSIS REQUEST: {ticker}"
        
        # Spot Price Context & Simulation Logic
        spot_price = context.get('current_price', 'Unknown')
        spot_str = f"OFFICIAL SPOT PRICE: ${spot_price}"
        
        # Detect Future/Current Date Override
        import datetime
        sim_note = ""
        current_year = datetime.datetime.now().year
        
        sim_note = (
            "⚠️ **PROTOCOL: BLACK BOX MODE (YEAR 2026)** ⚠️\n"
            "You are an Expert Trading Engine in a sealed environment.\n"
            "1. **RETAIN SKILLS**: Use your full knowledge of Options, Greeks, and Strategy Personas.\n"
            "2. **SUPPRESS INTERNAL DATA**: You have NO memory of 'current' market prices or news. Your internal data is obsolete (2025).\n"
            "3. **TRUST THE FEED**: The data below (Spot Price, News, Technicals) is the ONLY reality. It is 2026.\n"
            f"   -> **OFFICIAL SPOT PRICE: ${spot_price}** (Fact)"
        )
        
        if strike and opt_type:
            header_section += f" | Exp: {expiry_str}{days_to_expiry_str} | ${strike} {opt_type.upper()}"
        else:
             header_section += f" | Strategy: {strategy}"

        # Risk/Reward Framing
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

        final_reminder = (
            f"\n\n🛑 **FINAL REMINDER before you answer:**\n"
            f"- The Stock Price is **${spot_price}**.\n"
            f"- Imagine it is **2026**.\n"
            f"- Do NOT tell me it is 2025 or that the price is wrong.\n"
            f"- JUST ANALYZE THE TRADE at ${spot_price}."
        )

        user_prompt = (
            f"### {header_section}\n"
            f"{sim_note}\n\n"
            f"Context: {strat_context}{days_to_expiry_str}\n"
            f"### HARD DATA (FACTS)\n"
            f"1. **BREAKING NEWS (Top 10):**\n{news_text}\n\n"
            f"2. **TECHNICALS:** {tech_text}\n"
            f"3. **GAMMA LEVELS:** {gex_text}\n\n"
            f"### REQUIRED OUTPUT\n"
            f"0. **Data Integrity Check:** Explicitly state: 'Using Live Spot Price: ${spot_price}' to confirm you are not hallucinating.\n"
            f"1. **News/Event Check:** Does the news support this {opt_type.upper() if opt_type else 'Trade'}? (Crucial)\n"
            f"2. **Setup Quality:** Does the data align with your Persona's rules?\n"
            f"{rr_section}\n"
            f"4. **Trade Viability:** Is strictly this ${strike if strike else 'ATM'} {opt_type if opt_type else 'Play'} reasonable?\n"
            f"5. **Verdict:** [SAFE / RISKY / AVOID]\n"
            f"6. **Conviction Score:** (0-100) where >70 is Safe/Buy, <40 is Avoid."
            f"{final_reminder}"
        )

        payload = {
            "model": self.model, 
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1 # Low temp for factual/critical analysis
        }

        try:
            print(f"DEBUG: Calling Perplexity ({self.model}) for {ticker}...", flush=True)
            response = requests.post(self.base_url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code != 200:
                print(f"Perplexity API Error: {response.text}", flush=True)
                return {"error": f"API Error: {response.status_code}"}
                
            data = response.json()
            content = data['choices'][0]['message']['content']
            
            # Parse metrics from the text
            score = self._extract_score(content)
            verdict = self._extract_verdict(content)
            
            return {
                "ticker": ticker,
                "strategy": strategy,
                "analysis": content, # pure markdown
                "score": score,
                "verdict": verdict
            }
            
        except Exception as e:
            print(f"Reasoning Engine Failed: {e}", flush=True)
            return {"error": str(e)}

    def _extract_score(self, text):
        """Extract 'Conviction Score: 85' from text"""
        try:
            # Matches: "Conviction Score: 85" or "**Conviction Score:** 85"
            match = re.search(r"Conviction Score:.*?(\d{1,3})", text, re.IGNORECASE)
            if match:
                val = int(match.group(1))
                return min(100, max(0, val)) # Clamp 0-100
            return 0 # Default to 0 (Risk!) if not found
        except:
            return 0

    def _extract_verdict(self, text):
        """Extract Classification"""
        upper_text = text.upper()
        if "VERDICT: SAFE" in upper_text or "VERDICT:** SAFE" in upper_text: return "SAFE"
        if "VERDICT: AVOID" in upper_text or "VERDICT:** AVOID" in upper_text: return "AVOID"
        if "VERDICT: RISKY" in upper_text or "VERDICT:** RISKY" in upper_text: return "RISKY"
        
        # Fallback keyword search
        if "AVOID" in upper_text: return "AVOID"
        if "RISKY" in upper_text: return "RISKY"
        if "SAFE" in upper_text: return "SAFE"
        
        return "NEUTRAL"
