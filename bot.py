import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
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
# ORDER MODAL
# ----------------------------
class OrderModal(discord.ui.Modal, title="Place Order"):

    item = discord.ui.TextInput(label="Item")
    company = discord.ui.TextInput(label="Company")
    link = discord.ui.TextInput(label="Link")
    price = discord.ui.TextInput(label="Price")

    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="e.g. 1"
    )

    notes = discord.ui.TextInput(
        label="Notes (optional)",
        required=False,
        placeholder="Promo code, specs, urgency, etc."
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            item = self.item.value.strip()
            company = self.company.value.strip()
            link = self.link.value.strip()

            price = re.sub(r"[^0-9.]", "", self.price.value) or "0"
            quantity = re.sub(r"[^0-9]", "", self.quantity.value) or "1"
            notes = self.notes.value.strip() if self.notes.value else ""

            timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

            # ----------------------------
            # GOOGLE SHEETS WRITE
            # ----------------------------
            if sheet:
                sheet.append_row([
                    item,
                    company,
                    link,
                    price,
                    quantity,
                    notes,
                    interaction.user.name,
                    timestamp
                ])

            total = float(price) * int(quantity)

            # PRIVATE RESPONSE
            await interaction.followup.send(
                f"✅ Order placed: **{item} x{quantity}** (Total: ${total:.2f})",
                ephemeral=True
            )

            # PUBLIC LOG
            await interaction.channel.send(
                f"📦 **New Order Logged**\n"
                f"**Item:** {item}\n"
                f"**Company:** {company}\n"
                f"**Price:** ${price}\n"
                f"**Quantity:** {quantity}\n"
                f"**Notes:** {notes if notes else 'None'}\n"
                f"**User:** {interaction.user.mention}\n"
                f"**Time:** {timestamp}"
            )

        except Exception as e:
            print("❌ MODAL ERROR:")
            traceback.print_exc()

            await interaction.followup.send(
                "❌ Something went wrong while submitting your order.",
                ephemeral=True
            )


# ----------------------------
# /ORDER COMMAND (NO RESTRICTIONS)
# ----------------------------
@bot.tree.command(name="order", description="Place a robotics order")
async def order(interaction: discord.Interaction):
    try:
        await interaction.response.send_modal(OrderModal())

    except Exception as e:
        print("❌ ORDER COMMAND ERROR:", e)

        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Could not open order form.",
                ephemeral=True
            )


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
