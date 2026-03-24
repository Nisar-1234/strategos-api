"""
Source Bias Registry — Seed data for L1 editorial source credibility scoring.

Bias scoring methodology:
  - credibility_score (0-10): factual accuracy, editorial independence
  - political_lean (-5 to +5): -5 = far left, 0 = center, +5 = far right
  - ownership_type: "state", "corporate", "independent", "public"
  - agenda_flags: known editorial biases

Data informed by Media Bias/Fact Check and AllSides ratings.
In production, DeBERTa fine-tuned model will supplement these static scores.
"""

SEED_SOURCES = [
    # Tier 1: High credibility international wire services
    {
        "name": "Reuters",
        "layer": "L1",
        "ownership_type": "corporate",
        "credibility_score": 8.5,
        "political_lean": 0.0,
        "agenda_flags": [],
    },
    {
        "name": "Associated Press",
        "layer": "L1",
        "ownership_type": "independent",
        "credibility_score": 8.3,
        "political_lean": 0.0,
        "agenda_flags": [],
    },
    {
        "name": "AFP",
        "layer": "L1",
        "ownership_type": "public",
        "credibility_score": 8.0,
        "political_lean": -0.5,
        "agenda_flags": [],
    },

    # Tier 2: Major international broadcasters
    {
        "name": "BBC News",
        "layer": "L1",
        "ownership_type": "public",
        "credibility_score": 7.8,
        "political_lean": -0.5,
        "agenda_flags": ["UK-perspective"],
    },
    {
        "name": "Al Jazeera",
        "layer": "L1",
        "ownership_type": "state",
        "credibility_score": 6.5,
        "political_lean": -1.0,
        "agenda_flags": ["Qatar-aligned", "Middle-East-focus"],
    },
    {
        "name": "Deutsche Welle",
        "layer": "L1",
        "ownership_type": "public",
        "credibility_score": 7.5,
        "political_lean": -0.5,
        "agenda_flags": ["EU-perspective"],
    },

    # Tier 3: US major networks
    {
        "name": "CNN",
        "layer": "L1",
        "ownership_type": "corporate",
        "credibility_score": 6.8,
        "political_lean": -1.5,
        "agenda_flags": ["US-centric", "sensationalism"],
    },
    {
        "name": "Fox News",
        "layer": "L1",
        "ownership_type": "corporate",
        "credibility_score": 5.5,
        "political_lean": 3.0,
        "agenda_flags": ["US-right", "opinion-heavy"],
    },
    {
        "name": "MSNBC",
        "layer": "L1",
        "ownership_type": "corporate",
        "credibility_score": 5.8,
        "political_lean": -3.0,
        "agenda_flags": ["US-left", "opinion-heavy"],
    },
    {
        "name": "The New York Times",
        "layer": "L1",
        "ownership_type": "corporate",
        "credibility_score": 7.5,
        "political_lean": -1.0,
        "agenda_flags": ["US-establishment"],
    },
    {
        "name": "The Washington Post",
        "layer": "L1",
        "ownership_type": "corporate",
        "credibility_score": 7.3,
        "political_lean": -1.0,
        "agenda_flags": ["US-establishment"],
    },

    # Tier 4: State-controlled media (low credibility, high propaganda risk)
    {
        "name": "RT (Russia Today)",
        "layer": "L1",
        "ownership_type": "state",
        "credibility_score": 3.0,
        "political_lean": 0.0,
        "agenda_flags": ["Russia-state", "propaganda", "disinformation-risk"],
    },
    {
        "name": "Xinhua",
        "layer": "L1",
        "ownership_type": "state",
        "credibility_score": 3.5,
        "political_lean": 0.0,
        "agenda_flags": ["China-state", "CCP-aligned"],
    },
    {
        "name": "IRNA",
        "layer": "L1",
        "ownership_type": "state",
        "credibility_score": 2.5,
        "political_lean": 0.0,
        "agenda_flags": ["Iran-state", "theocratic-aligned"],
    },
    {
        "name": "TASS",
        "layer": "L1",
        "ownership_type": "state",
        "credibility_score": 3.0,
        "political_lean": 0.0,
        "agenda_flags": ["Russia-state"],
    },
    {
        "name": "KCNA",
        "layer": "L1",
        "ownership_type": "state",
        "credibility_score": 1.0,
        "political_lean": 0.0,
        "agenda_flags": ["DPRK-state", "propaganda"],
    },

    # Tier 5: Regional/specialty conflict reporting
    {
        "name": "The Times of Israel",
        "layer": "L1",
        "ownership_type": "corporate",
        "credibility_score": 6.5,
        "political_lean": 1.0,
        "agenda_flags": ["Israel-perspective"],
    },
    {
        "name": "Haaretz",
        "layer": "L1",
        "ownership_type": "corporate",
        "credibility_score": 7.0,
        "political_lean": -1.5,
        "agenda_flags": ["Israel-left"],
    },
    {
        "name": "Kyiv Independent",
        "layer": "L1",
        "ownership_type": "independent",
        "credibility_score": 6.8,
        "political_lean": 0.0,
        "agenda_flags": ["Ukraine-perspective", "pro-Ukraine"],
    },

    # Signal data sources (non-editorial, high credibility)
    {
        "name": "MarineTraffic AIS",
        "layer": "L3",
        "ownership_type": "corporate",
        "credibility_score": 9.5,
        "political_lean": 0.0,
        "agenda_flags": [],
    },
    {
        "name": "FlightRadar24",
        "layer": "L4",
        "ownership_type": "corporate",
        "credibility_score": 9.5,
        "political_lean": 0.0,
        "agenda_flags": [],
    },
    {
        "name": "Alpha Vantage",
        "layer": "L5",
        "ownership_type": "corporate",
        "credibility_score": 9.0,
        "political_lean": 0.0,
        "agenda_flags": [],
    },
    {
        "name": "Metals-API",
        "layer": "L5",
        "ownership_type": "corporate",
        "credibility_score": 8.5,
        "political_lean": 0.0,
        "agenda_flags": [],
    },
    {
        "name": "Open Exchange Rates",
        "layer": "L6",
        "ownership_type": "corporate",
        "credibility_score": 9.0,
        "political_lean": 0.0,
        "agenda_flags": [],
    },
    {
        "name": "Cloudflare Radar",
        "layer": "L10",
        "ownership_type": "corporate",
        "credibility_score": 9.5,
        "political_lean": 0.0,
        "agenda_flags": [],
    },
    {
        "name": "IODA Georgia Tech",
        "layer": "L10",
        "ownership_type": "independent",
        "credibility_score": 9.2,
        "political_lean": 0.0,
        "agenda_flags": [],
    },
]

SEED_CONFLICTS = [
    {
        "name": "Gaza Conflict",
        "region": "Middle East",
        "status": "active",
        "description": "Israeli-Palestinian conflict centered on Gaza Strip. Multi-party escalation involving IDF operations, Hamas resistance, and regional actors including Hezbollah and Houthi militants.",
    },
    {
        "name": "Ukraine Conflict",
        "region": "Eastern Europe",
        "status": "active",
        "description": "Russia-Ukraine war following 2022 invasion. Active frontline conflict with NATO support for Ukraine, sanctions on Russia, and global energy/food supply chain disruption.",
    },
    {
        "name": "Taiwan Strait",
        "region": "East Asia",
        "status": "monitoring",
        "description": "Cross-strait tensions between China and Taiwan. Military posturing, ADIZ incursions, and diplomatic competition with US involvement. Potential flash point for great power conflict.",
    },
    {
        "name": "Sudan Civil War",
        "region": "East Africa",
        "status": "active",
        "description": "Civil war between SAF and RSF factions. Humanitarian crisis, mass displacement, and regional destabilization across the Sahel.",
    },
    {
        "name": "Iran Nuclear",
        "region": "Middle East",
        "status": "monitoring",
        "description": "Iran's nuclear enrichment program and regional proxy network. Tensions with Israel and US over enrichment levels, IAEA inspections, and regional influence.",
    },
    {
        "name": "Yemen/Houthi",
        "region": "Middle East",
        "status": "active",
        "description": "Houthi attacks on Red Sea shipping and Saudi targets. Linked to Iran proxy network. Direct impact on global maritime trade via Bab el-Mandeb strait.",
    },
    {
        "name": "Syria Instability",
        "region": "Middle East",
        "status": "monitoring",
        "description": "Post-civil war fragmentation with multiple actors. Turkish operations in north, Israeli strikes on Iranian assets, US presence in northeast, Russian bases on Mediterranean.",
    },
    {
        "name": "Myanmar Civil War",
        "region": "Southeast Asia",
        "status": "active",
        "description": "Post-coup resistance against military junta. Ethnic armed organizations and People's Defense Force fighting military government. Humanitarian crisis.",
    },
]
