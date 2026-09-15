"""
Shared constants for the one-click demo accounts, used by both the
`seed_data` management command (which creates/resets them) and the login
page (which renders a quick-login tile for each one).
"""

DEMO_PASSWORD = "Demo@123"

# (username, group, first name, last name, is_staff)
DEMO_USERS = [
    ("demo_admin", "Super Admin", "Ava", "Admin", True),
    ("demo_management", "Management", "Marcus", "Rao", False),
    ("demo_sales", "Salesperson", "Priya", "Sales", False),
    ("demo_measurement", "Measurement Staff", "Karthik", "Site", False),
    ("demo_production", "Production Staff", "Suresh", "Floor", False),
    ("demo_dispatch", "Dispatch Staff", "Divya", "Logistics", False),
    ("demo_installation", "Installation Team", "Arjun", "Install", False),
    ("demo_service", "Service/Maintenance Staff", "Meena", "Support", False),
]

DEMO_ICONS = {
    "Super Admin": "fa-crown",
    "Management": "fa-chart-line",
    "Salesperson": "fa-handshake",
    "Measurement Staff": "fa-ruler-combined",
    "Production Staff": "fa-industry",
    "Dispatch Staff": "fa-truck",
    "Installation Team": "fa-screwdriver-wrench",
    "Service/Maintenance Staff": "fa-headset",
}
