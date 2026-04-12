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

# ----------------------------
# DISCORD SETUP
# ----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

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
# FIND NEXT EMPTY ROW
# ----------------------------
def get_next_row(sheet):
    col = sheet.col_values(1)
    return len([x for x in col if x.strip() != ""]) + 1


# ----------------------------
# CATEGORY DROPDOWN
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
            item, company, link, price, quantity, notes = self.data

            timestamp = datetime.now(
                ZoneInfo("America/Chicago")
            ).strftime("%d/%m/%Y %I:%M %p")

            # WRITE TO SHEET
            if sheet:
                row = get_next_row(sheet)

                sheet.update(
                    f"A{row}:I{row}",
                    [[
                        item,
                        company,
                        link,
                        price,
                        quantity,
                        notes,
                        category,
                        interaction.user.name,
                        timestamp
                    ]],
                    value_input_option="USER_ENTERED"
                )

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
                f"**Price:** {price}\n"
                f"**Quantity:** {quantity}\n"
                f"**Category:** {category}\n"
                f"**Notes:** {notes if notes else 'None'}\n"
                f"**User:** {interaction.user.mention}\n"
                f"**Time:** {timestamp}"
            )

            # remove dropdown after use
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
            item, company, link, price, quantity = self.data

            notes = self.notes.value.strip() if self.notes.value else ""

            view = CategoryView((item, company, link, price, quantity, notes))

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
# CONTINUE BUTTON VIEW (FIXED FLOW)
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

    item = discord.ui.TextInput(label="Item")
    company = discord.ui.TextInput(label="Company")
    link = discord.ui.TextInput(label="Link")
    price = discord.ui.TextInput(label="Price")
    quantity = discord.ui.TextInput(label="Quantity", placeholder="e.g. 1")

    async def on_submit(self, interaction: discord.Interaction):

        try:
            item = self.item.value.strip()
            company = self.company.value.strip()
            link = self.link.value.strip()

            price_raw = re.sub(r"[^0-9.]", "", self.price.value) or "0"
            quantity_raw = re.sub(r"[^0-9]", "", self.quantity.value) or "1"

            price = float(price_raw)
            quantity = int(quantity_raw)

            data = (item, company, link, price, quantity)

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
# COMMAND
# ----------------------------
@bot.tree.command(name="order", description="Place a robotics order")
async def order(interaction: discord.Interaction):
    await interaction.response.send_modal(OrderModal())


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
