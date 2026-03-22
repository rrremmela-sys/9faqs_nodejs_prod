"""
=============================================================
ZENERAL BOT PLATFORM — CLIENT CONFIGURATION
=============================================================
Add new clients here. Each client gets:
  - Their own bot personality
  - Their own catalog (courses/rooms/services)
  - Their own AI system prompt
  - Their own welcome & fallback messages

TO ADD A NEW CLIENT:
  1. Copy the template at the bottom
  2. Fill in the details
  3. Set CLIENT_ID env variable in Render to activate
=============================================================
"""

CLIENTS = {

    # ============================================================
    # CLIENT 1: 9faqs — Online Learning Platform
    # ============================================================
    "9faqs": {
        "name":          "9faqs",
        "business_type": "edtech",
        "website":       "https://9faqs.com",
        "enroll_url":    "https://9faqs.com/enroll",
        "phone":         "919666416600",

        "welcome": (
            "👋 *Welcome to 9faqs!*\n\n"
            "Your gateway to tech careers 🚀\n\n"
            "Please choose:\n"
            "1️⃣ View Courses\n"
            "2️⃣ Enroll Now\n"
            "3️⃣ Talk to Counselor\n\n"
            "Or just ask me anything!"
        ),
        "fallback":     "I'm not sure about that 🤔\n\nType *Hi* to see our courses or *3* to talk to a counselor.",
        "support_msg":  "📞 Connecting you to a counselor...\nA human agent will reply shortly! ⏳",
        "catalog_label": "Courses",

        "catalog": {
            "crash_course": {
                "name":        "Python Crash Course",
                "price":       "₹1999",
                "duration":    "Weekend (Sat & Sun, 10AM–4PM)",
                "emoji":       "🐍",
                "description": "Fast-track live Python training with AI tools intro. Certificate included.",
                "url":         "https://9faqs.com/training/python_crash_course",
                "highlights":  ["Live instructor-led", "AI tools intro", "Git & Jira", "Certificate"],
            },
            "bootcamp": {
                "name":        "Python Bootcamp",
                "price":       "Contact us",
                "duration":    "90 days Mon–Fri + 3mo internship",
                "emoji":       "🚀",
                "description": "Beginner to advanced Python with cloud lab, career prep & internship.",
                "url":         "https://9faqs.com/training/python_bootcamp",
                "highlights":  ["Cloud lab support", "Hands-on projects", "Mock interviews", "Internship"],
            },
            "ai_workshop": {
                "name":        "AI Workshop",
                "price":       "₹1999",
                "duration":    "4-hour live workshop",
                "emoji":       "🤖",
                "description": "Build a website using AI tools. No coding needed. 1-1 post support.",
                "url":         "https://9faqs.com/training/ai_workshops",
                "highlights":  ["Build website with AI", "ChatGPT + Cursor IDE", "Domain & hosting", "1-1 support"],
            },
            "python_faqs": {
                "name":        "Python FAQs (Free)",
                "price":       "Free",
                "duration":    "Self-paced",
                "emoji":       "📚",
                "description": "1736+ Python interview questions with adaptive learning.",
                "url":         "https://9faqs.com/python",
                "highlights":  ["1736+ questions", "Adaptive learning", "Interview prep", "Free forever"],
            },
        },

        "faqs": [
            {"q": "best for beginners",    "a": "🚀 Python Bootcamp — 90 days, cloud lab, internship. Or try Crash Course (₹1999 weekend)."},
            {"q": "working professionals", "a": "🐍 Python Crash Course — weekend batches, intensive, ₹1999."},
            {"q": "certificate",           "a": "🎓 Yes! Crash Course & Bootcamp both give Certificate of Completion."},
            {"q": "job guarantee",         "a": "No job guarantee, but we provide profile building & mock interviews."},
            {"q": "telugu",                "a": "Yes! Sessions available in Telugu 🇮🇳. Enroll at 9faqs.com/enroll"},
            {"q": "internship",            "a": "Yes! Python Bootcamp includes optional 3-month internship."},
            {"q": "alumni",                "a": "9FAQs Alumni get 10% discount on future courses! 🎉"},
        ],

        "system_prompt": (
            "You are a helpful WhatsApp assistant for 9faqs (https://9faqs.com), "
            "an online tech learning platform in India.\n\n"
            "COURSES:\n"
            "1. Python Crash Course — ₹1999, weekend, live, certificate\n"
            "2. Python Bootcamp — 90 days Mon-Fri, internship, cloud lab\n"
            "3. AI Workshop — ₹1999, 4-hour live, build website with AI\n"
            "4. Python FAQs — Free self-learning, 1736+ questions\n\n"
            "KEY INFO:\n"
            "- All sessions are LIVE (not recorded)\n"
            "- Available in Telugu language\n"
            "- Alumni get 10% discount\n"
            "- Enroll: https://9faqs.com/enroll\n\n"
            "RULES:\n"
            "- Keep answers SHORT (2-4 lines) — this is WhatsApp\n"
            "- Be warm and encouraging\n"
            "- Always suggest enrolling\n"
            "- Never make up info\n"
            "- Reply in user's language"
        ),
    },

    # ============================================================
    # CLIENT 2: Resort Demo
    # ============================================================
    "resort_demo": {
        "name":          "Sunset Resort",
        "business_type": "hospitality",
        "website":       "https://sunsetresort.com",
        "enroll_url":    "https://sunsetresort.com/book",
        "phone":         "",

        "welcome": (
            "🌅 *Welcome to Sunset Resort!*\n\n"
            "Your perfect getaway awaits 🏖️\n\n"
            "Please choose:\n"
            "1️⃣ View Rooms\n"
            "2️⃣ Book Now\n"
            "3️⃣ Talk to Concierge"
        ),
        "fallback":      "I'm not sure about that 🤔\n\nType *Hi* to see our rooms or *3* to talk to our team.",
        "support_msg":   "🛎️ Connecting you to our concierge...\nWe'll reply shortly! ⏳",
        "catalog_label": "Rooms",

        "catalog": {
            "deluxe": {
                "name":        "Deluxe Room",
                "price":       "₹5000/night",
                "duration":    "Min 1 night",
                "emoji":       "🛏️",
                "description": "Comfortable room with garden view, AC, WiFi and all amenities.",
                "url":         "https://sunsetresort.com/rooms/deluxe",
                "highlights":  ["Garden view", "King size bed", "Free WiFi", "Breakfast included"],
            },
            "suite": {
                "name":        "Premium Suite",
                "price":       "₹8000/night",
                "duration":    "Min 1 night",
                "emoji":       "👑",
                "description": "Luxury suite with sea view, jacuzzi and butler service.",
                "url":         "https://sunsetresort.com/rooms/suite",
                "highlights":  ["Sea view", "Jacuzzi", "Butler service", "All meals included"],
            },
            "villa": {
                "name":        "Private Villa",
                "price":       "₹15000/night",
                "duration":    "Min 2 nights",
                "emoji":       "🏡",
                "description": "Private villa with pool, garden and personal chef.",
                "url":         "https://sunsetresort.com/rooms/villa",
                "highlights":  ["Private pool", "Personal chef", "Garden", "Full privacy"],
            },
        },

        "faqs": [
            {"q": "check in",    "a": "Check-in: 2 PM | Check-out: 11 AM. Early check-in available on request."},
            {"q": "pool",        "a": "Yes! We have a main pool (6AM-9PM) and private pool in villas."},
            {"q": "food",        "a": "Restaurant open 7AM-10PM. Room service available 24/7."},
            {"q": "parking",     "a": "Free parking available for all guests."},
            {"q": "pet",         "a": "Sorry, pets are not allowed at the resort."},
        ],

        "system_prompt": (
            "You are a helpful WhatsApp assistant for Sunset Resort, a luxury resort.\n\n"
            "ROOMS:\n"
            "1. Deluxe Room — ₹5000/night, garden view, breakfast\n"
            "2. Premium Suite — ₹8000/night, sea view, jacuzzi\n"
            "3. Private Villa — ₹15000/night, private pool, chef\n\n"
            "Check-in: 2PM | Check-out: 11AM\n"
            "Restaurant: 7AM-10PM | Room service: 24/7\n\n"
            "RULES:\n"
            "- Keep answers SHORT — this is WhatsApp\n"
            "- Be warm and luxurious in tone\n"
            "- Always encourage booking\n"
            "- Reply in user's language"
        ),
    },

    # ============================================================
    # CLIENT 3: Clinic Demo
    # ============================================================
    "clinic_demo": {
        "name":          "HealthFirst Clinic",
        "business_type": "healthcare",
        "website":       "https://healthfirst.com",
        "enroll_url":    "https://healthfirst.com/book",
        "phone":         "",

        "welcome": (
            "🏥 *Welcome to HealthFirst Clinic!*\n\n"
            "Your health is our priority 💚\n\n"
            "Please choose:\n"
            "1️⃣ View Services\n"
            "2️⃣ Book Appointment\n"
            "3️⃣ Talk to Our Team"
        ),
        "fallback":      "I'm not sure about that 🤔\n\nType *Hi* to see our services or *3* to talk to our team.",
        "support_msg":   "👨‍⚕️ Connecting you to our team...\nWe'll reply shortly! ⏳",
        "catalog_label": "Services",

        "catalog": {
            "general": {
                "name":        "General Consultation",
                "price":       "₹500",
                "duration":    "30 minutes",
                "emoji":       "🩺",
                "description": "General health checkup and consultation with experienced doctor.",
                "url":         "https://healthfirst.com/services/general",
                "highlights":  ["Experienced doctors", "Same day appointment", "Follow-up included"],
            },
            "dental": {
                "name":        "Dental Care",
                "price":       "₹800",
                "duration":    "45 minutes",
                "emoji":       "🦷",
                "description": "Complete dental checkup, cleaning and consultation.",
                "url":         "https://healthfirst.com/services/dental",
                "highlights":  ["Painless treatment", "Modern equipment", "All dental services"],
            },
            "lab": {
                "name":        "Lab Tests",
                "price":       "From ₹300",
                "duration":    "Results in 24hrs",
                "emoji":       "🔬",
                "description": "Complete blood work, urine tests and diagnostic tests.",
                "url":         "https://healthfirst.com/services/lab",
                "highlights":  ["Home collection", "Digital reports", "NABL certified"],
            },
        },

        "faqs": [
            {"q": "timing",      "a": "Clinic hours: Mon-Sat 9AM-8PM. Sunday 9AM-1PM."},
            {"q": "emergency",   "a": "For emergencies please call 108. We handle non-emergency cases."},
            {"q": "insurance",   "a": "Yes, we accept most major insurance providers."},
            {"q": "home visit",  "a": "Home visits available for senior citizens. Extra charges apply."},
        ],

        "system_prompt": (
            "You are a helpful WhatsApp assistant for HealthFirst Clinic.\n\n"
            "SERVICES:\n"
            "1. General Consultation — ₹500, 30 min\n"
            "2. Dental Care — ₹800, 45 min\n"
            "3. Lab Tests — from ₹300, results in 24hrs\n\n"
            "Timings: Mon-Sat 9AM-8PM, Sunday 9AM-1PM\n\n"
            "RULES:\n"
            "- Keep answers SHORT — this is WhatsApp\n"
            "- Be caring and professional\n"
            "- Always encourage booking appointment\n"
            "- For emergencies, refer to 108\n"
            "- Reply in user's language"
        ),
    },
}

# ============================================================
# TEMPLATE — Copy this to add a new client
# ============================================================
CLIENT_TEMPLATE = {
    "your_client_id": {                          # e.g. "zomato_branch_1"
        "name":          "Business Name",
        "business_type": "type",                 # edtech/hospitality/healthcare/retail/etc
        "website":       "https://website.com",
        "enroll_url":    "https://website.com/contact",
        "phone":         "91XXXXXXXXXX",

        "welcome": (
            "👋 *Welcome to Business Name!*\n\n"
            "Brief tagline here.\n\n"
            "Please choose:\n"
            "1️⃣ View Products/Services\n"
            "2️⃣ Order/Book Now\n"
            "3️⃣ Talk to Our Team"
        ),
        "fallback":      "I'm not sure about that.\n\nType *Hi* to start or *3* to talk to our team.",
        "support_msg":   "Connecting you to our team...",
        "catalog_label": "Products",             # or Services/Rooms/Courses

        "catalog": {
            "item_1": {
                "name":        "Product/Service Name",
                "price":       "₹XXX",
                "duration":    "Duration or delivery time",
                "emoji":       "🎯",
                "description": "Brief description",
                "url":         "https://website.com/item",
                "highlights":  ["Feature 1", "Feature 2", "Feature 3"],
            },
        },

        "faqs": [
            {"q": "keyword", "a": "Answer to common question"},
        ],

        "system_prompt": (
            "You are a helpful WhatsApp assistant for Business Name.\n\n"
            "PRODUCTS/SERVICES:\n"
            "List them here.\n\n"
            "RULES:\n"
            "- Keep answers SHORT — this is WhatsApp\n"
            "- Be friendly\n"
            "- Always encourage purchase/booking\n"
            "- Reply in user's language"
        ),
    },
}


def get_client(client_id):
    """Get client config by ID. Falls back to 9faqs if not found."""
    return CLIENTS.get(client_id, CLIENTS["9faqs"])

def list_clients():
    """List all configured clients."""
    return [
        {
            "id":            k,
            "name":          v["name"],
            "business_type": v.get("business_type", ""),
            "catalog_count": len(v.get("catalog", {})),
        }
        for k, v in CLIENTS.items()
    ]

if __name__ == "__main__":
    print("=== Zeneral Bot Platform — Clients ===")
    for c in list_clients():
        print(f"  {c['id']:20} → {c['name']} ({c['business_type']}, {c['catalog_count']} items)")
