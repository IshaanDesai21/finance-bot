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
# MODAL (PRIVATE FORM)
# ----------------------------
class ExpenseModal(discord.ui.Modal, title="Log Expense"):

    item = discord.ui.TextInput(
        label="Item (be specific)",
        placeholder="e.g. NEO motor, gearbox, controller"
    )

    company = discord.ui.TextInput(label="Company")
    link = discord.ui.TextInput(label="Link")
    price = discord.ui.TextInput(label="Price")

    async def on_submit(self, interaction: discord.Interaction):

        # CLEAN DATA
        item_clean = self.item.value.strip()
        company_clean = self.company.value.strip().title()

        # remove $ and non-numeric chars except dot
        price_clean = re.sub(r"[^0-9.]", "", self.price.value)

        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

        # GOOGLE SHEETS WRITE
        sheet.append_row([
            item_clean,
            company_clean,
            self.link.value,
            price_clean,
            interaction.user.name,
            timestamp
        ])

        # PRIVATE RESPONSE
        await interaction.response.send_message(
            f"✅ Added **{item_clean}** (${price_clean})",
            ephemeral=True
        )

        # PUBLIC LOG
        await interaction.channel.send(
            f"📦 **New Expense Logged**\n"
            f"**Item:** {item_clean}\n"
            f"**Company:** {company_clean}\n"
            f"**Price:** ${price_clean}\n"
            f"**User:** {interaction.user.mention}\n"
            f"**Time:** {timestamp}"
        )


# ----------------------------
# ROLE PROTECTION
# ----------------------------
@bot.tree.command(name="expense", description="Log a robotics expense")
async def expense(interaction: discord.Interaction):

    officer_role = discord.utils.get(interaction.user.roles, name="Officer")

    if officer_role is None:
        await interaction.response.send_message(
            "❌ You do not have permission to use this command.",
            ephemeral=True
        )
        return

    await interaction.response.send_modal(ExpenseModal())


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
