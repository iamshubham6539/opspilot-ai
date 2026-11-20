import reflex as rx

# The Reflex backend runs on 8001 so it does not collide with the OpsPilot API
# on 8000. Change both api_url and backend_port together if you move it.
config = rx.Config(
    app_name="opspilot_ui",
    api_url="http://localhost:8001",
    backend_port=8001,
    frontend_port=3000,
    telemetry_enabled=False,
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(),
    ],
)
