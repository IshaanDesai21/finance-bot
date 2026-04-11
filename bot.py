import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re

# ----------------------------
# DISCORD SETUP
# ----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------------
# GOOGLE SHEETS SETUP
# ----------------------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json",
    scope
)

client = gspread.authorize(creds)
sheet = client.open("Robotics Budget").sheet1


# ----------------------------
# MODAL (PRIVATE INPUT FORM)
# ----------------------------
class ExpenseModal(discord.ui.Modal, title="Log Expense"):

    item = discord.ui.TextInput(
        label="Item (be specific)",
        placeholder="e.g. NEO motor, not just 'motor'"
    )

    company = discord.ui.TextInput(label="Company")
    link = discord.ui.TextInput(label="Link")
    price = discord.ui.TextInput(label="Price")

    async def on_submit(self, interaction: discord.Interaction):

        # ----------------------------
        # CLEAN DATA
        # ----------------------------

        item_clean = self.item.value.strip()

        company_clean = self.company.value.strip().title()

        # remove $ and any non-number except dot
        price_clean = re.sub(r"[^0-9.]", "", self.price.value)

        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

        # ----------------------------
        # GOOGLE SHEETS WRITE
        # ----------------------------
        sheet.append_row([
            item_clean,
            company_clean,
            self.link.value,
            price_clean,
            interaction.user.name,
            timestamp
        ])

        # ----------------------------
        # PRIVATE RESPONSE
        # ----------------------------
        await interaction.response.send_message(
            f"✅ Added **{item_clean}** (${price_clean})",
            ephemeral=True
        )

        # ----------------------------
        # PUBLIC MESSAGE
        # ----------------------------
        await interaction.channel.send(
            f"📦 **New Expense Logged**\n"
            f"**Item:** {item_clean}\n"
            f"**Company:** {company_clean}\n"
            f"**Price:** ${price_clean}\n"
            f"**User:** {interaction.user.mention}\n"
            f"**Time:** {timestamp}"
        )


# ----------------------------
# ROLE + COMMAND CHECK
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
# RUN BOT
# ----------------------------
bot.run("YOUR_BOT_TOKEN")
