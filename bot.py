import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json
import re

# ----------------------------
# DISCORD SETUP
# ----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------------
# GOOGLE SHEETS AUTH (RAILWAY SAFE)
# ----------------------------
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


# ----------------------------
# ORDER MODAL
# ----------------------------
class OrderModal(discord.ui.Modal, title="Place Order"):

    item = discord.ui.TextInput(
        label="Item",
        placeholder="e.g. NEO motor, gearbox, controller"
    )

    company = discord.ui.TextInput(
        label="Company"
    )

    link = discord.ui.TextInput(
        label="Link"
    )

    price = discord.ui.TextInput(
        label="Price"
    )

    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="e.g. 1, 2, 5"
    )

    notes = discord.ui.TextInput(
        label="Notes (optional)",
        required=False,
        placeholder="Promo code, urgency, specs, etc."
    )

    async def on_submit(self, interaction: discord.Interaction):

        # CLEAN DATA
        item_clean = self.item.value.strip()
        company_clean = self.company.value.strip().title()

        price_clean = re.sub(r"[^0-9.]", "", self.price.value)
        quantity_clean = re.sub(r"[^0-9]", "", self.quantity.value)
        quantity_clean = quantity_clean if quantity_clean else "1"

        notes_clean = self.notes.value.strip() if self.notes.value else ""

        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

        # GOOGLE SHEETS WRITE
        sheet.append_row([
            item_clean,
            company_clean,
            self.link.value,
            price_clean,
            quantity_clean,
            notes_clean,
            interaction.user.name,
            timestamp
        ])

        total_cost = float(price_clean or 0) * int(quantity_clean)

        # PRIVATE RESPONSE
        await interaction.response.send_message(
            f"✅ Order placed: **{item_clean} x{quantity_clean}** "
            f"(Total: ${total_cost:.2f})",
            ephemeral=True
        )

        # PUBLIC LOG
        await interaction.channel.send(
            f"📦 **New Order Logged**\n"
            f"**Item:** {item_clean}\n"
            f"**Company:** {company_clean}\n"
            f"**Price:** ${price_clean}\n"
            f"**Quantity:** {quantity_clean}\n"
            f"**Notes:** {notes_clean if notes_clean else 'None'}\n"
            f"**User:** {interaction.user.mention}\n"
            f"**Time:** {timestamp}"
        )


# ----------------------------
# /ORDER COMMAND (NO ROLE CHECK)
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
    print(f"Logged in as {bot.user}")


# ----------------------------
# RUN BOT (RAILWAY SAFE)
# ----------------------------
bot.run(os.getenv("DISCORD_TOKEN"))
