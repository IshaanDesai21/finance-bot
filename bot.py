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

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        scope
    )

    client = gspread.authorize(creds)
    sheet = client.open("Robotics Budget").sheet1

    print("✅ Google Sheets connected")

except Exception as e:
    print("❌ Google Sheets FAILED:", e)
    sheet = None


# ----------------------------
# STEP 2 MODAL (NOTES)
# ----------------------------
class NotesModal(discord.ui.Modal, title="Additional Notes"):

    def __init__(self, item, company, link, price, quantity):
        super().__init__()
        self.item = item
        self.company = company
        self.link = link
        self.price = price
        self.quantity = quantity

    notes = discord.ui.TextInput(
        label="Notes (optional)",
        required=False,
        placeholder="Promo code, urgency, specs..."
    )

    async def on_submit(self, interaction: discord.Interaction):

        try:
            await interaction.response.defer(ephemeral=True)

            # ----------------------------
            # CLEAN INPUTS
            # ----------------------------
            item_clean = str(self.item).strip()
            company_clean = str(self.company).strip()
            link_clean = str(self.link).strip()

            price_clean = re.sub(r"[^0-9.]", "", str(self.price).strip()) or "0"
            quantity_clean = re.sub(r"[^0-9]", "", str(self.quantity).strip()) or "1"

            price_float = float(price_clean)
            quantity_int = int(quantity_clean)

            notes_clean = self.notes.value.strip() if self.notes.value else ""

            timestamp = datetime.now(
                ZoneInfo("America/Chicago")
            ).strftime("%d/%m/%Y %I:%M %p")

            # ----------------------------
            # GOOGLE SHEETS ROW (FIXED ORDER)
            # ----------------------------
            if sheet:
                sheet.append_row([
                    item_clean,
                    company_clean,
                    link_clean,
                    price_float,     # REAL NUMBER (fixes apostrophe issue)
                    quantity_int,    # REAL NUMBER
                    notes_clean,
                    interaction.user.name,
                    timestamp
                ], value_input_option="USER_ENTERED")

            total = price_float * quantity_int

            # clickable item
            item_linked = f"[{item_clean}]({link_clean})" if link_clean else item_clean

            await interaction.followup.send(
                f"✅ Order placed: **{item_clean} x{quantity_int}** (Total: ${total:.2f})",
                ephemeral=True
            )

            await interaction.channel.send(
                f"📦 **New Order Logged**\n"
                f"**Item:** {item_linked}\n"
                f"**Company:** {company_clean}\n"
                f"**Price:** {price_float}\n"
                f"**Quantity:** {quantity_int}\n"
                f"**Notes:** {notes_clean if notes_clean else 'None'}\n"
                f"**User:** {interaction.user.mention}\n"
                f"**Time:** {timestamp}"
            )

            try:
                await interaction.message.edit(view=None)
            except:
                pass

        except Exception:
            traceback.print_exc()

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Failed to submit order.",
                    ephemeral=True
                )


# ----------------------------
# STEP 1 MODAL
# ----------------------------
class OrderModal(discord.ui.Modal, title="Place Order"):

    item = discord.ui.TextInput(label="Item")
    company = discord.ui.TextInput(label="Company")
    link = discord.ui.TextInput(label="Link")
    price = discord.ui.TextInput(label="Price")
    quantity = discord.ui.TextInput(label="Quantity", placeholder="e.g. 1")

    async def on_submit(self, interaction: discord.Interaction):

        view = NotesButtonView(
            item=self.item.value,
            company=self.company.value,
            link=self.link.value,
            price=self.price.value,
            quantity=self.quantity.value
        )

        await interaction.response.send_message(
            "✅ Step 1 complete. Click below to finish your order.",
            view=view,
            ephemeral=True
        )


# ----------------------------
# BUTTON VIEW
# ----------------------------
class NotesButtonView(discord.ui.View):

    def __init__(self, item, company, link, price, quantity):
        super().__init__(timeout=120)

        self.item = item
        self.company = company
        self.link = link
        self.price = price
        self.quantity = quantity

    @discord.ui.button(
        label="Add Notes & Finish Order",
        style=discord.ButtonStyle.green
    )
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_modal(
            NotesModal(
                self.item,
                self.company,
                self.link,
                self.price,
                self.quantity
            )
        )


# ----------------------------
# /ORDER COMMAND
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
