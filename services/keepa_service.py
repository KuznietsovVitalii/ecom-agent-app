import streamlit as st
import pandas as pd
import keepa
import requests
import numpy as np
from datetime import datetime

# Constants
KEEPA_BASE_URL = "https://api.keepa.com"

class KeepaService:
    def __init__(self, api_key):
        self.api_key = api_key
        self.api = keepa.Keepa(api_key, timeout=60)

    @st.cache_data(ttl=3600)
    def get_product_info(_self, asins, domain_id=1, **kwargs):
        """
        Fetches product info using direct HTTP request for flexibility.
        Cached for 1 hour.
        """
        if not _self.api_key: return {"error": "Keepa API Key not provided."}
        
        if isinstance(asins, str):
            asins = [s.strip() for s in asins.split(',') if s.strip()]
        if not asins:
            return {"error": "ASIN parameter is empty."}

        params = {'key': _self.api_key, 'domain': domain_id, 'asin': ','.join(asins)}
        if kwargs.get('stats_days'): params['stats'] = kwargs.get('stats_days')
        if kwargs.get('include_rating'): params['rating'] = 1
        if kwargs.get('include_history'): params['history'] = 1
        if kwargs.get('limit_days'): params['days'] = kwargs.get('limit_days')
        if kwargs.get('include_offers'): params['offers'] = 100
        if kwargs.get('include_buybox'): params['buybox'] = 1
        if kwargs.get('force_update_hours') is not None: params['update'] = kwargs.get('force_update_hours')
        
        try:
            response = requests.get(f"{KEEPA_BASE_URL}/product", params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": f"API request failed with status {e.response.status_code if e.response else 'N/A'}. Reason: {e}"}

    def get_keepa_product(self, asin, domain="US"):
        return KeepaProduct(self.api_key, asin, domain)

class KeepaProduct:
    # create sales ranges (min - max)
    sales_tiers: dict = {
        -1: 0,
        0: 50,
        50: 100,
        100: 200,
        200: 300,
        300: 400,
        400: 500,
        500: 600,
        600: 700,
        700: 800,
        800: 900,
        900: 1000,
        1000: 2000,
        2000: 3000,
        3000: 4000,
        4000: 5000,
        5000: 6000,
        6000: 7000,
        7000: 8000,
        8000: 9000,
        9000: 10000,
        10000: 20000,
        20000: 30000,
        30000: 40000,
        40000: 50000,
        50000: 60000,
        60000: 70000,
        70000: 80000,
        80000: 90000,
        90000: 100000,
        100000: 150000,
    }

    def __init__(self, api_key, asin=None, domain="US"):
        self.api_key = api_key
        self.exists: bool = False
        self.asin: str = asin
        self.domain: str = domain
        self.title: str | None = None
        self.image: str | None = None
        self.data: list | None = None
        self.brand: str | None = None
        self.parent: str | None = None
        self.pivot: pd.DataFrame | None = None
        self.initial_days: int = 360
        self.variations = set()
        self.avg_price = 0
        self.api = keepa.Keepa(api_key, timeout=60)

    def __str__(self, days=30):
        self.get_last_days(days=days)
        if not self.exists:
            return f"{self.asin} does not exist or there is no Keepa data for it"
        return f"{self.asin}: {self.brand}\n{self.title}\nLatest {days} days sales: {self.min_sales:,.0f} - {self.max_sales:,.0f} units ({self.avg_sales:,.0f} average)\nAverage price last {days} days: \$ {self.avg_price:.2f}, total sales: \$ {(self.avg_sales*self.avg_price):,.0f}"

    def _format_numbers(self, df):
        if "full price" in df.columns:
            df["full price"] = round(df["full price"], 2)
        if "final price" in df.columns:
            df["final price"] = round(df["final price"], 2)
        if "sales max" in df.columns:
            df["sales max"] = df.loc[~df["sales max"].isnull(), "sales max"].astype(int)
        if "sales min" in df.columns:
            df["sales min"] = df.loc[~df["sales min"].isnull(), "sales min"].astype(int)
        if "LD" in df.columns:
            df["LD"] = round(df["LD"], 2)
        return df

    def query(self):
        if not self.data:
            try:
                # Using the instance's api object
                self.data = self.api.query(self.asin, domain=self.domain)
            except Exception:
                self.data = [{}]

    def convert_time(self, keepa_time: int) -> pd.Timestamp | str:
        """function that converts time from keepa format to datetime format"""
        if keepa_time == 0:
            return "unknown"
        converted = (keepa_time + 21564000) * 60000
        converted = pd.to_datetime(converted, unit="ms")
        return converted

    def apply_sales_tiers(self, x):
        """map minimal sales tiers to sales tiers dict to get min-max sales"""
        if x == -1:
            return 0
        return KeepaProduct.sales_tiers.get(x, x * 1.3)

    def pull_sales(self):
        if not self.data:
            self.query()
        elif self.data == "Not found":
            return
        
        if not self.data or not self.data[0]:
             return

        self.title = self.data[0].get("title")
        img_links = self.data[0].get("imagesCSV")
        if img_links and len(img_links.split(",")) > 0:
            self.image = (
                "https://m.media-amazon.com/images/I/" + img_links.split(",")[0]
            )
        self.brand = self.data[0].get("brand")
        self.parent = self.data[0].get("parentAsin")
        sales = self.data[0].get("data", {}).get("df_NEW", pd.DataFrame())
        if len(sales) > 0:
            self.exists = True
        else:
            return
        sales = sales.rename(columns={"value": "full price"}).fillna(-1)
        self.last_sales_date = sales.index[-1]
        return sales

    def pull_coupons(self):
        sales = self.pull_sales()
        if not self.exists:
            return
        coupons = self.data[0].get("couponHistory")
        if coupons:
            times = [self.convert_time(x) for x in coupons[::3]]
            discounts = coupons[1::3]
            perc_off = [
                x if x < 0 else 0 for x in discounts
            ]  # separate % off discounts
            money_off = [
                x / 100 if x > 0 else 0 for x in discounts
            ]  # separate $ off discounts
            sns_coupons = coupons[2::3]
            sns_perc_off = [
                x if x < 0 else 0 for x in sns_coupons
            ]  # separate % off sns
            sns_money_off = [
                x / 100 if x > 0 else 0 for x in sns_coupons
            ]  # separate $ off sns

            coupon_history = pd.DataFrame(
                data=list(zip(perc_off, money_off, sns_perc_off, sns_money_off)),
                index=times,
                columns=["% off", "$ off", "SNS %", "SNS $"],
            )
        else:
            coupon_history = pd.DataFrame(
                [[0, 0, 0, 0]],
                index=[self.last_sales_date],
                columns=["% off", "$ off", "SNS %", "SNS $"],
            )

        sales_history = pd.merge(
            sales, coupon_history, how="outer", left_index=True, right_index=True
        ).ffill()
        return sales_history

    def pull_lds(self):
        sales_history = self.pull_coupons()
        if not self.exists:
            return
        lds = (
            self.data[0]
            .get("data", {})
            .get(
                "df_LIGHTNING_DEAL",
                pd.DataFrame([0], index=[self.last_sales_date], columns=["LD"]),
            )
        )
        lds = lds.fillna(0)
        lds = lds.rename(columns={"value": "LD"})

        sales_history = (
            pd.merge(sales_history, lds, how="outer", left_index=True, right_index=True)
            .ffill()
            .fillna(0)
        )
        return sales_history

    def pull_bsr(self):
        sales_history = self.pull_lds()
        if not self.exists:
            return
        bsr = (
            self.data[0]
            .get("data", {})
            .get(
                "df_SALES",
                pd.DataFrame([np.nan], index=[self.last_sales_date], columns=["BSR"]),
            )
            .replace(-1, np.nan)
        )
        bsr = bsr.rename(columns={"value": "BSR"})
        sales_history = pd.merge(
            sales_history, bsr, how="outer", left_index=True, right_index=True
        ).ffill()
        sales_history["final price"] = (
            (
                sales_history["full price"]
                - sales_history["$ off"]
                - sales_history["SNS $"]
            )
            * (1 + sales_history["% off"] / 100)
            * (1 + sales_history["SNS %"] / 100)
        )

        sales_history.loc[sales_history["LD"] != 0, "final price"] = sales_history["LD"]
        return sales_history

    def pull_monthly_sold(self):
        sales_history = self.pull_bsr()
        if not self.exists:
            return
        monthly_sold = self.data[0].get("monthlySoldHistory")
        if monthly_sold:
            times = [self.convert_time(x) for x in monthly_sold[::2]]
            monthly_units = monthly_sold[1::2]
            monthly_sold_history = pd.DataFrame(
                data=monthly_units, index=times, columns=["monthlySoldMin"]
            )
        else:
            monthly_sold_history = pd.DataFrame(
                [-1], index=[self.last_sales_date], columns=["monthlySoldMin"]
            )
        monthly_sold_history["monthlySoldMax"] = monthly_sold_history[
            "monthlySoldMin"
        ].map(self.apply_sales_tiers)
        monthly_sold_history = monthly_sold_history.replace(-1, 0)

        self.sales_history_monthly = pd.merge(
            sales_history,
            monthly_sold_history,
            how="outer",
            left_index=True,
            right_index=True,
        ).ffill()
        return self.sales_history_monthly

    def generate_daily_sales(self, days=360):
        self.short_history = self.pull_monthly_sold()
        if not self.exists:
            return
        self.short_history["sales min"] = self.short_history["monthlySoldMin"] / (
            60 * 24 * 30
        )
        self.short_history["sales max"] = self.short_history["monthlySoldMax"] / (
            60 * 24 * 30
        )

        lifetime = pd.date_range(
            (pd.to_datetime("today") - pd.Timedelta(days=days)).date(),
            self.short_history.index.max(),
            freq="min",
        )

        lifetime_df = pd.DataFrame(index=lifetime)
        minutely_history = pd.merge(
            lifetime_df,
            self.short_history,
            how="left",
            left_index=True,
            right_index=True,
        ).ffill()
        # remove price info with full price == -1 product blocked
        minutely_history.loc[minutely_history["full price"] == -1, "final price"] = np.nan
        minutely_history["full price"] = minutely_history["full price"].replace(-1, np.nan)

        # trim minutely history into short history
        self.short_history = minutely_history.copy()
        sum_cols = self.short_history.columns
        self.short_history["sum1"] = self.short_history[sum_cols].sum(axis=1)
        self.short_history["sum2"] = self.short_history[sum_cols].shift(-1).sum(axis=1)
        self.short_history["sum3"] = self.short_history[sum_cols].shift(1).sum(axis=1)

        self.short_history["diff"] = (
            self.short_history["sum1"] - self.short_history["sum2"]
        ) + (self.short_history["sum1"] - self.short_history["sum3"])
        self.short_history = self.short_history[self.short_history["diff"] != 0][
            sum_cols
        ]

        minutely_history["date"] = minutely_history.index.date
        self.pivot = minutely_history.pivot_table(
            values=[
                "full price",
                "% off",
                "$ off",
                "SNS %",
                "SNS $",
                "LD",
                "final price",
                "sales min",
                "sales max",
                "BSR",
            ],
            index="date",
            aggfunc={
                "full price": "mean",
                "% off": "min",
                "$ off": "min",
                "SNS %": "min",
                "SNS $": "min",
                "LD": "max",
                "final price": "mean",
                "sales min": "sum",
                "sales max": "sum",
                "BSR": "min",
            },
        )
        if "full price" not in self.pivot.columns:
            self.pivot["full price"] = np.nan
        if "sales min" not in self.pivot.columns:
            self.pivot["sales min"] = np.nan
        if "sales max" not in self.pivot.columns:
            self.pivot["sales max"] = np.nan

        self.short_history["LD"] = self.short_history["LD"].replace(0, np.nan)
        self.short_history["full price"] = self.short_history["full price"].replace(
            -1, np.nan
        )
        self.short_history["coupon"] = (
            (
                minutely_history["full price"]
                - minutely_history["$ off"]
                - minutely_history["SNS $"]
            )
            * (1 + minutely_history["% off"] / 100)
            * (1 + minutely_history["SNS %"] / 100)
        )
        self.short_history.loc[
            self.short_history["coupon"] == self.short_history["full price"], "coupon"
        ] = np.nan
        self.pivot = self._format_numbers(self.pivot)
        self.pivot = self.pivot.replace(0, np.nan)

    def get_last_days(self, days=360):
        self.generate_daily_sales(days=days)
        if not self.exists:
            return
        if self.pivot is None:
            raise BaseException("self.pivot is not initialized")
        self.last_days = self.pivot[
            self.pivot.index
            >= (pd.to_datetime("today") - pd.Timedelta(days=days)).date()
        ]
        self.last_days["asin"] = self.asin
        self.min_sales = int(self.last_days["sales min"].sum())
        self.max_sales = int(self.last_days["sales max"].sum())
        self.avg_sales = (self.min_sales + self.max_sales) / 2
        self.full_price = self.last_days["full price"].mean()
        if "final price" in self.last_days.columns:
            self.avg_price = self.last_days["final price"].mean()

    def get_sales_history_by_date(self):
        """
        Fetches and formats the monthly sales history into a date-by-date table.
        """
        if not self.data:
            self.query()
        if not self.exists:
            return pd.DataFrame()

        monthly_sold = self.data[0].get("monthlySoldHistory")
        if not monthly_sold:
            return pd.DataFrame()

        times = [self.convert_time(x) for x in monthly_sold[::2]]
        monthly_units = monthly_sold[1::2]
        
        history_df = pd.DataFrame(
            data=list(zip(times, monthly_units)),
            columns=["Date", "Min Sales"]
        )
        
        history_df = history_df[history_df["Min Sales"] != -1].reset_index(drop=True)
        if history_df.empty:
            return pd.DataFrame()

        history_df["Max Sales"] = history_df["Min Sales"].map(self.apply_sales_tiers)
        history_df["Avg Sales"] = (history_df["Min Sales"] * 0.9 + history_df["Max Sales"] * 0.1).astype(int)
        
        return history_df[["Date", "Min Sales", "Max Sales", "Avg Sales"]]
