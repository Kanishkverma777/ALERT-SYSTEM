# 🚨 Navjeevan Alert System

An AI-powered disaster response triage system that analyzes emergency reports in real-time and automatically locates nearby resources using LangGraph orchestration, Groq LLMs, and live web search.

![Disaster Alert System](https://img.shields.io/badge/Status-Active-brightgreen) ![Python](https://img.shields.io/badge/Python-3.11+-blue) ![License](https://img.shields.io/badge/License-MIT-yellow)

## 🎯 Overview

**Navjeevan** (meaning "new life" in Hindi) is an intelligent disaster response system that:

- **Analyzes** disaster reports using AI to extract critical information
- **Classifies** incident types (flood, fire, earthquake, building collapse, etc.)
- **Assesses** severity and priority based on casualties and impact
- **Locates** nearby medical facilities, rescue teams, and emergency resources
- **Generates** actionable response plans for emergency coordinators
- **Visualizes** incident locations and resources on an interactive map

The system uses a graph-based AI pipeline built with LangGraph that processes reports through multiple specialized nodes running in parallel for maximum efficiency.

## ✨ Key Features

### 🤖 AI-Powered Analysis
- Multi-stage LLM pipeline using Groq's GPT-OSS models
- Automatic incident classification across 8 disaster types
- Intelligent severity assessment with rule-based escalation
- Entity extraction (location, casualties, needs)

### 🗺️ Resource Discovery
- **Geocoding**: Converts place names to coordinates (Google Places API or OpenStreetMap)
- **Nearby Search**: Locates hospitals, fire stations, police stations, pharmacies within customizable radius
- **Web Search**: Finds NDRF/SDRF teams, control rooms, helplines via live Tavily search
- **Distance Calculation**: Ranks resources by proximity and capability

### 📊 Interactive Dashboard
- Real-time pipeline execution tracking
- Severity badges (Critical, High, Medium, Low)
- Interactive map with incident location and resource markers
- Route visualization from incident to resources
- Emergency helplines reference (112, 108, 101, etc.)

### 🎨 Premium UI
- Dark theme with glassmorphism design
- Monospace typography (Inter + JetBrains Mono)
- Responsive layout for all screen sizes
- Color-coded severity indicators

## 🏗️ Architecture

```
┌─────────────┐
│   Report    │
│   Input     │
└──────┬──────┘
       │
       ▼
   ┌───────┐
   │Analyze│──► Is Emergency? ──No──► [Flag & Stop]
   └───┬───┘                    
       │Yes                     
       ▼                        
   ┌────────┐                  
   │Classify│ ──► Disaster Type
   └───┬────┘                  
       │                       
       ▼                       
   ┌────────┐                  
   │Extract │ ──► Entities + Geocode
   └───┬────┘                  
       │                       
       ▼                       
   ┌────────┐                  
   │Severity│ ──► Severity + Priority
   └───┬────┘                  
       │                       
       ├──────────┬──────────┐ (Parallel)
       ▼          ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐
   │Medical │ │Rescue  │ │General │
   │Resources│ │Resources│ │Resources│
   └───┬────┘ └───┬────┘ └───┬────┘
       └──────────┴──────────┘
                  │
                  ▼
              ┌──────┐
              │ Plan │ ──► Action Plan
              └──┬───┘
                 │
                 ▼
              ┌────────┐
              │Respond │ ──► Final Report
              └────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- API Keys:
  - [Groq API](https://console.groq.com/) (required)
  - [Tavily Search API](https://tavily.com/) (required)
  - [Google Maps API](https://developers.google.com/maps) (optional, uses OpenStreetMap if not provided)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/alert-system.git
   cd alert-system
   ```

2. **Set up environment**
   ```bash
   # Create virtual environment
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt
   ```

   Or using `uv` (faster):
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

3. **Configure API keys**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and add your API keys:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   TAVILY_API_KEY=your_tavily_api_key_here
   # Optional:
   # GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
   ```

### Running the Application

#### Web Interface (Streamlit)
```bash
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

#### Command Line Interface
```bash
# Interactive mode
python navjeevan.py

# One-shot analysis
python navjeevan.py "A 5-storey building has collapsed in Saket, Delhi. Several people are feared trapped."

# View pipeline graph
python navjeevan.py --graph
```

## 📖 Usage Examples

### Example 1: Building Collapse
```
INPUT: "A 5-storey building has collapsed in Saket, Delhi. Several people are feared trapped under the debris."

OUTPUT:
✓ Disaster Type: BUILDING_COLLAPSE
✓ Location: Saket, Delhi (28.5245°N, 77.2066°E)
✓ Severity: HIGH
✓ Priority: CRITICAL
✓ People Affected: reported, count unknown
✓ Resources Found: 12 facilities within 10km
  - Max Super Speciality Hospital [2.1 km]
  - Fortis Hospital [3.4 km]
  - Delhi Fire Station [1.8 km]
✓ Action Plan: 6 steps generated
```

### Example 2: Flood
```
INPUT: "Heavy rainfall has caused severe waterlogging in Hiranandani area, Mumbai. 200+ residents stranded on rooftops."

OUTPUT:
✓ Disaster Type: FLOOD
✓ Severity: CRITICAL
✓ People Affected: 200+
✓ Needs: rescue, food, water, evacuation
✓ Resources: NDRF teams, boats, emergency shelters
```

## 🛠️ Project Structure

```
alert-system/
├── app.py              # Streamlit web interface
├── navjeevan.py        # Core LangGraph pipeline
├── geo.py              # Geocoding & nearby search
├── pyproject.toml      # Project metadata & dependencies
├── .env.example        # Environment template
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## 🔧 Configuration

### Disaster Types
The system recognizes:
- `FLOOD` - Inundation, waterlogging, river overflow
- `FIRE` - Building fires, forest fires
- `EARTHQUAKE` - Seismic events
- `BUILDING_COLLAPSE` - Structural failures
- `ROAD_ACCIDENT` - Vehicle collisions
- `LANDSLIDE` - Hillside collapses
- `CYCLONE` - Tropical storms
- `OTHER` - Other emergencies

### Resource Categories
- **Medical**: Hospitals, clinics, pharmacies, ambulances
- **Rescue**: NDRF/SDRF teams, fire stations, police stations
- **Supplies**: Relief camps, food distribution (via web search)

### Search Radius
- Medical facilities: 10 km
- Rescue resources: 5 km

Configurable in `geo.py`:
```python
RADIUS_M = {
    "medical": 10_000,
    "rescue": 5_000,
}
```

## 🧪 Testing

```bash
# Run with test data
python navjeevan.py "Fire at commercial building in Connaught Place, Delhi. 50 people evacuated, 5 injured."

# View execution graph
python navjeevan.py --graph > pipeline.mmd
```

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📋 Roadmap

- [ ] Multi-language support (Hindi, regional languages)
- [ ] Voice input for emergency reports
- [ ] SMS/WhatsApp integration
- [ ] Historical incident database
- [ ] Predictive analytics for disaster hotspots
- [ ] Mobile app (React Native)
- [ ] Integration with government emergency services

## ⚠️ Limitations

- **Not a replacement** for official emergency services (always call 112/108/101)
- Resource data is **unverified** - contact facilities directly to confirm availability
- Web search may return outdated or incorrect information
- Requires internet connectivity
- LLM responses may occasionally be inaccurate

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **LangGraph** - Graph-based LLM orchestration
- **Groq** - Fast LLM inference
- **Tavily** - Real-time web search
- **OpenStreetMap** - Free geocoding & POI data
- **Streamlit** - Rapid web app development

## 📞 Emergency Helplines (India)

- **112** - National Emergency
- **108** - Ambulance
- **101** - Fire Brigade
- **100** - Police
- **1078** - NDMA Disaster Management

## 📧 Contact

For questions or support, please open an issue on GitHub.

---

**⚡ Built with urgency, designed for impact.**
