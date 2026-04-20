import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import json
import re
import traceback
import random

# ----------------------------
# DISCORD SETUP
# ----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------------
# PERSISTENT TEAM STORAGE
# user_teams[user_id] = {"team": "FRC", "full_name": "Ishaan Desai"}
# ----------------------------
TEAMS_FILE = "user_teams.json"

def load_teams():
    if os.path.exists(TEAMS_FILE):
        with open(TEAMS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_teams():
    with open(TEAMS_FILE, "w") as f:
        json.dump(user_teams, f)

user_teams = load_teams()

# Helper: get team string for a user
def get_team(user_id: str) -> str | None:
    entry = user_teams.get(user_id)
    if isinstance(entry, dict):
        return entry.get("team")
    # Legacy support: plain string stored before this update
    if isinstance(entry, str):
        return entry
    return None

# Helper: get display name (full name if set, else Discord username)
def get_display_name(user_id: str, fallback_username: str) -> str:
    entry = user_teams.get(user_id)
    if isinstance(entry, dict):
        return entry.get("full_name") or fallback_username
    return fallback_username

# ----------------------------
# GOOGLE SHEETS SETUP
# ----------------------------
sheet = None

try:
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

    client = gspread.authorize(creds)
    sheet = client.open("Westwood Finances").sheet1

    print("✅ Google Sheets connected")

except Exception as e:
    print("❌ Google Sheets FAILED:", e)
    sheet = None


# ----------------------------
# FAKE PARTS FOR /test
# ----------------------------
TEST_PARTS = [
    ("Test Servo Motor",       "ServoKing",     "https://example.com/servo",    12.99,  2,  "hardware"),
    ("Test Limit Switch",      "ElectroSupply", "https://example.com/switch",    3.49,  5,  "hardware"),
    ("Test Aluminum Bracket",  "MetalDepot",    "https://example.com/bracket",   8.75,  4,  "hardware"),
    ("Test Arduino Nano",      "RoboShop",      "https://example.com/arduino",  22.00,  1,  "hardware"),
    ("Test Rubber Wheel",      "WheelWorld",    "https://example.com/wheel",    15.50,  3,  "hardware"),
    ("Test Battery Pack",      "PowerCell",     "https://example.com/battery",  34.99,  1,  "hardware"),
    ("Test Steel Bolt Set",    "BoltBarn",      "https://example.com/bolts",     6.25, 10,  "hardware"),
    ("Test CAD License",       "AutodeskTest",  "https://example.com/cad",      49.99,  1,  "software"),
    ("Test Zip Ties (100pk)",  "FastenerPro",   "https://example.com/zipties",   4.99,  2,  "miscellaneous"),
    ("Test Bearing Kit",       "SpinRight",     "https://example.com/bearings", 18.40,  2,  "hardware"),
]


# ----------------------------
# FIND NEXT EMPTY ROW
# ----------------------------
def get_next_row(sheet):
    col = sheet.col_values(1)
    return len([x for x in col if x.strip() != ""]) + 1


# ----------------------------
# SHARED WRITE TO SHEET
# Column layout:
# A=item, B=company, C=link, D=price, E=quantity,
# F=notes, G=category, H=team, I=timestamp,
# J=total (formula), K=Pending Review,
# (L-M gap), N=order count formula,
# O=full name (or username if not set)
# ----------------------------
def write_order_to_sheet(sheet, row, item, company, link, price, quantity,
                          notes, category, team, timestamp, display_name):

    total_formula  = f"=PRODUCT(D{row}:E{row})"
    pending_review = "Pending Review"
    count_formula  = f'=IF(A{row}<>"", COUNTIF($A$3:A{row}, "<>"), "")'

    sheet.update(
        f"A{row}:K{row}",
        [[
            item,
            company,
            link,
            price,
            quantity,
            notes,
            category.capitalize(),
            team,
            timestamp,
            total_formula,
            pending_review
        ]],
        value_input_option="USER_ENTERED"
    )

    sheet.update(
        f"N{row}",
        [[count_formula]],
        value_input_option="USER_ENTERED"
    )

    sheet.update(
        f"O{row}",
        [[display_name]],          # Full name instead of username
        value_input_option="USER_ENTERED"
    )

    return price * quantity


# ----------------------------
# FULL NAME MODAL (shown after team selection)
# ----------------------------
class FullNameModal(discord.ui.Modal, title="Enter Your Official Name"):

    def __init__(self, team: str):
        super().__init__()
        self.team = team

    full_name = discord.ui.TextInput(
        label="Official First and Last Name",
        placeholder="e.g. Ishaan Desai",
        min_length=2,
        max_length=80,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.full_name.value.strip()

        user_teams[str(interaction.user.id)] = {
            "team": self.team,
            "full_name": name,
        }
        save_teams()

        await interaction.response.edit_message(
            content=(
                f"✅ You've been assigned to **{self.team}** as **{name}**!\n"
                f"You can now use `/order`."
            ),
            view=None
        )


# ----------------------------
# TEAM DROPDOWN (for /set-team)
# ----------------------------
class TeamSelectView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        placeholder="Select your team",
        options=[
            discord.SelectOption(label="FRC",         value="FRC"),
            discord.SelectOption(label="Kunai",       value="Kunai"),
            discord.SelectOption(label="Hunga Munga", value="Hunga Munga"),
            discord.SelectOption(label="Atl Atl",     value="Atl Atl"),
            discord.SelectOption(label="Slingshot",   value="Slingshot"),
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        team = select.values[0]
        # Open the name modal — team is saved only after name is confirmed
        await interaction.response.send_modal(FullNameModal(team))


# ----------------------------
# CATEGORY DROPDOWN (for /order)
# ----------------------------
class CategoryView(discord.ui.View):

    def __init__(self, data):
        super().__init__(timeout=120)
        self.data = data

    @discord.ui.select(
        placeholder="Select a category",
        options=[
            discord.SelectOption(label="Hardware"),
            discord.SelectOption(label="Software"),
            discord.SelectOption(label="Outreach"),
            discord.SelectOption(label="Food"),
            discord.SelectOption(label="Miscellaneous"),
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):

        try:
            category = select.values[0].lower()
            item, company, link, price, quantity, notes, team, display_name = self.data

            timestamp = datetime.now(
                ZoneInfo("America/Chicago")
            ).strftime("%m/%d/%Y %I:%M %p")

            if sheet:
                row   = get_next_row(sheet)
                total = write_order_to_sheet(
                    sheet, row, item, company, link, price, quantity,
                    notes, category, team, timestamp, display_name
                )
            else:
                total = price * quantity

            item_linked = f"[{item}]({link})" if link else item

            await interaction.response.send_message(
                f"✅ Order placed: **{item} x{quantity}** (Total: ${total:.2f})",
                ephemeral=True
            )

            await interaction.channel.send(
                f"📦 **New Order Logged**\n"
                f"**Item:** {item_linked}\n"
                f"**Company:** {company}\n"
                f"**Price:** ${price:.2f}\n"
                f"**Quantity:** {quantity}\n"
                f"**Total:** ${total:.2f}\n"
                f"**Category:** {category.capitalize()}\n"
                f"**Notes:** {notes if notes else 'None'}\n"
                f"**Team:** {team}\n"
                f"**User:** {interaction.user.mention} ({display_name})\n"
                f"**Time:** {timestamp}"
            )

            await interaction.message.edit(view=None)

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Failed to finalize order.",
                    ephemeral=True
                )


# ----------------------------
# NOTES MODAL
# ----------------------------
class NotesModal(discord.ui.Modal, title="Finalize Order"):

    def __init__(self, data):
        super().__init__()
        self.data = data

    notes = discord.ui.TextInput(
        label="Notes (optional)",
        required=False,
        placeholder="Promo code, urgency, specs..."
    )

    async def on_submit(self, interaction: discord.Interaction):

        try:
            item, company, link, price, quantity, team, display_name = self.data
            notes = self.notes.value.strip() if self.notes.value else ""

            view = CategoryView((item, company, link, price, quantity, notes, team, display_name))

            await interaction.response.send_message(
                "Select a category to finish your order:",
                view=view,
                ephemeral=True
            )

        except Exception:
            traceback.print_exc()
            await interaction.response.send_message(
                "❌ Failed to process notes.",
                ephemeral=True
            )


# ----------------------------
# CONTINUE BUTTON VIEW
# ----------------------------
class ContinueView(discord.ui.View):

    def __init__(self, data):
        super().__init__(timeout=120)
        self.data = data

    @discord.ui.button(label="Continue Order", style=discord.ButtonStyle.green)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NotesModal(self.data))


# ----------------------------
# ORDER MODAL
# ----------------------------
class OrderModal(discord.ui.Modal, title="Place Order"):

    item     = discord.ui.TextInput(label="Item")
    company  = discord.ui.TextInput(label="Company")
    link     = discord.ui.TextInput(label="Link")
    price    = discord.ui.TextInput(label="Price")
    quantity = discord.ui.TextInput(label="Quantity", placeholder="e.g. 1")

    def __init__(self, team: str, display_name: str):
        super().__init__()
        self.team         = team
        self.display_name = display_name

    async def on_submit(self, interaction: discord.Interaction):

        try:
            item     = self.item.value.strip()
            company  = self.company.value.strip()
            link     = self.link.value.strip()

            price_raw    = re.sub(r"[^0-9.]", "", self.price.value) or "0"
            quantity_raw = re.sub(r"[^0-9]",  "", self.quantity.value) or "1"

            price    = float(price_raw)
            quantity = int(quantity_raw)

            data = (item, company, link, price, quantity, self.team, self.display_name)
            view = ContinueView(data)

            await interaction.response.send_message(
                "Click to continue your order:",
                view=view,
                ephemeral=True
            )

        except Exception:
            traceback.print_exc()
            await interaction.response.send_message(
                "❌ Failed to start order.",
                ephemeral=True
            )


# ----------------------------
# TEST PASSWORD MODAL
# ----------------------------
class TestPasswordModal(discord.ui.Modal, title="Test Order Authentication"):

    password = discord.ui.TextInput(
        label="Password",
        placeholder="Enter password to submit test order",
        required=True
    )

    def __init__(self, team: str, display_name: str):
        super().__init__()
        self.team         = team
        self.display_name = display_name

    async def on_submit(self, interaction: discord.Interaction):
        if self.password.value.strip() != "hi":
            await interaction.response.send_message(
                "❌ Incorrect password.",
                ephemeral=True
            )
            return

        try:
            item, company, link, price, quantity, category = random.choice(TEST_PARTS)
            notes     = "DISCORD TEST"
            timestamp = datetime.now(ZoneInfo("America/Chicago")).strftime("%m/%d/%Y %I:%M %p")
            row       = get_next_row(sheet)

            total = write_order_to_sheet(
                sheet, row, item, company, link, price, quantity,
                notes, category, self.team, timestamp, self.display_name
            )

            item_linked = f"[{item}]({link})"

            await interaction.response.send_message(
                f"🧪 **Test order submitted successfully!**\n"
                f"**Item:** {item}\n"
                f"**Company:** {company}\n"
                f"**Price:** ${price:.2f} x{quantity} = **${total:.2f}**\n"
                f"**Category:** {category.capitalize()}\n"
                f"**Team:** {self.team}\n"
                f"**Name on sheet:** {self.display_name}\n"
                f"**Row written:** {row}",
                ephemeral=True
            )

            await interaction.channel.send(
                f"🧪 **Test Order Logged**\n"
                f"**Item:** {item_linked}\n"
                f"**Company:** {company}\n"
                f"**Price:** ${price:.2f}\n"
                f"**Quantity:** {quantity}\n"
                f"**Total:** ${total:.2f}\n"
                f"**Category:** {category.capitalize()}\n"
                f"**Notes:** {notes}\n"
                f"**Team:** {self.team}\n"
                f"**User:** {interaction.user.mention} ({self.display_name})\n"
                f"**Time:** {timestamp}"
            )

        except Exception:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Test order failed. Check logs.",
                    ephemeral=True
                )


# ----------------------------
# SUMMARY HELPER
# ----------------------------
def build_summary(rows: list[list], month: int, year: int) -> discord.Embed:
    TEAMS      = ["FRC", "Kunai", "Hunga Munga", "Atl Atl", "Slingshot"]
    CATEGORIES = ["hardware", "software", "outreach", "food", "miscellaneous"]

    team_totals = {t: 0.0 for t in TEAMS}
    cat_totals  = {c: 0.0 for c in CATEGORIES}
    grand_total = 0.0
    order_count = 0

    for row in rows[1:]:  # skip header row
        if len(row) < 10:
            row += [""] * (10 - len(row))

        timestamp_str = row[8].strip()   # column I
        total_str     = row[9].strip()   # column J
        team          = row[7].strip()   # column H
        category      = row[6].strip()   # column G

        if not timestamp_str or not total_str:
            continue

        try:
            dt = datetime.strptime(timestamp_str, "%m/%d/%Y %I:%M %p")
        except ValueError:
            continue

        if dt.month != month or dt.year != year:
            continue

        try:
            total = float(total_str)
        except ValueError:
            continue

        grand_total += total
        order_count += 1

        if team in team_totals:
            team_totals[team] += total
        if category.lower() in cat_totals:
            cat_totals[category.lower()] += total

    month_name = datetime(year, month, 1).strftime("%B %Y")

    embed = discord.Embed(
        title=f"📊 Spending Summary — {month_name}",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="💰 Grand Total",
        value=f"**${grand_total:.2f}** across {order_count} order{'s' if order_count != 1 else ''}",
        inline=False
    )

    team_lines = "\n".join(
        f"`{t:<12}` ${v:.2f}" for t, v in team_totals.items() if v > 0
    ) or "No orders this month."
    embed.add_field(name="🤖 By Team", value=team_lines, inline=True)

    cat_lines = "\n".join(
        f"`{c.title():<14}` ${v:.2f}" for c, v in cat_totals.items() if v > 0
    ) or "No orders this month."
    embed.add_field(name="🗂️ By Category", value=cat_lines, inline=True)

    embed.set_footer(text="Data pulled from Westwood Finances sheet")
    return embed


# ----------------------------
# COMMANDS
# ----------------------------
@bot.tree.command(name="set-team", description="Set your team and official name (required before ordering)")
async def set_team(interaction: discord.Interaction):
    view = TeamSelectView()
    await interaction.response.send_message(
        "Select your team below, then you'll be asked for your official name. This only needs to be done once:",
        view=view,
        ephemeral=True
    )


@bot.tree.command(name="order", description="Place a robotics order")
async def order(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    team    = get_team(user_id)

    if not team:
        await interaction.response.send_message(
            "⚠️ You need to set your team first! Run `/set-team` once before placing orders.",
            ephemeral=True
        )
        return

    display_name = get_display_name(user_id, interaction.user.name)
    await interaction.response.send_modal(OrderModal(team, display_name))


@bot.tree.command(name="summary", description="View monthly spending summary by team and category")
async def summary(interaction: discord.Interaction):
    if not sheet:
        await interaction.response.send_message("❌ Google Sheets is not connected.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        now   = datetime.now(ZoneInfo("America/Chicago"))
        rows  = sheet.get_all_values()
        embed = build_summary(rows, now.month, now.year)
        await interaction.followup.send(embed=embed)

    except Exception:
        traceback.print_exc()
        await interaction.followup.send("❌ Failed to generate summary.")


@bot.tree.command(name="test", description="Submit a random test order to verify the bot and sheet are working")
async def test(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    team    = get_team(user_id)

    if not team:
        await interaction.response.send_message(
            "⚠️ You need to set your team first! Run `/set-team` once before using `/test`.",
            ephemeral=True
        )
        return

    if not sheet:
        await interaction.response.send_message("❌ Google Sheets is not connected.", ephemeral=True)
        return

    display_name = get_display_name(user_id, interaction.user.name)
    await interaction.response.send_modal(TestPasswordModal(team, display_name))


# ----------------------------
# READY EVENT
# ----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"🤖 Logged in as {bot.user}")


# ----------------------------
# RUN BOT
# ----------------------------
bot.run(os.getenv("DISCORD_TOKEN"))