"""
IMC Prosperity 4 — Data Model
Source: https://imc-prosperity.notion.site/writing-an-algorithm-in-python
Python 3.10 — Exact replica from the wiki
"""
import json
from typing import Dict, List
from json import JSONEncoder
import jsonpickle

Time = int
Symbol = str
Product = str
Position = int
UserId = str
ObservationValue = int


class Listing:
    def __init__(self, symbol: Symbol, product: Product, denomination: Product):
        self.symbol = symbol
        self.product = product
        self.denomination = denomination


class ConversionObservation:
    def __init__(
        self,
        bidPrice: float,
        askPrice: float,
        transportFees: float,
        exportTariff: float,
        importTariff: float,
        sugarPrice: float,
        sunlightIndex: float,
    ):
        self.bidPrice = bidPrice
        self.askPrice = askPrice
        self.transportFees = transportFees
        self.exportTariff = exportTariff
        self.importTariff = importTariff
        self.sugarPrice = sugarPrice
        self.sunlightIndex = sunlightIndex


class Observation:
    def __init__(
        self,
        plainValueObservations: Dict[Product, ObservationValue],
        conversionObservations: Dict[Product, ConversionObservation],
    ):
        self.plainValueObservations = plainValueObservations
        self.conversionObservations = conversionObservations


class Order:
    def __init__(self, symbol: Symbol, price: int, quantity: int) -> None:
        self.symbol = symbol
        self.price = price
        self.quantity = quantity

    def __str__(self) -> str:
        return "(" + self.symbol + ", " + str(self.price) + ", " + str(self.quantity) + ")"

    def __repr__(self) -> str:
        return "(" + self.symbol + ", " + str(self.price) + ", " + str(self.quantity) + ")"


class OrderDepth:
    def __init__(self, buy_orders: Dict[int, int] = None, sell_orders: Dict[int, int] = None):
        self.buy_orders = buy_orders if buy_orders is not None else {}
        self.sell_orders = sell_orders if sell_orders is not None else {}


class Trade:
    def __init__(
        self,
        symbol: Symbol,
        price: int,
        quantity: int,
        buyer: UserId = None,
        seller: UserId = None,
        timestamp: Time = 0,
    ) -> None:
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.buyer = buyer
        self.seller = seller
        self.timestamp = timestamp

    def __str__(self) -> str:
        return (
            "("
            + self.symbol
            + ", "
            + str(self.price)
            + ", "
            + str(self.quantity)
            + ", "
            + str(self.buyer)
            + ", "
            + str(self.seller)
            + ", "
            + str(self.timestamp)
            + ")"
        )

    def __repr__(self) -> str:
        return (
            "("
            + self.symbol
            + ", "
            + str(self.price)
            + ", "
            + str(self.quantity)
            + ", "
            + str(self.buyer)
            + ", "
            + str(self.seller)
            + ", "
            + str(self.timestamp)
            + ")"
        )


class TradingState(object):
    def __init__(
        self,
        traderData: str,
        timestamp: Time,
        listings: Dict[Symbol, Listing],
        order_depths: Dict[Symbol, OrderDepth],
        own_trades: Dict[Symbol, List[Trade]],
        market_trades: Dict[Symbol, List[Trade]],
        position: Dict[Symbol, Position],
        observations: Observation,
    ):
        self.traderData = traderData
        self.timestamp = timestamp
        self.listings = listings
        self.order_depths = order_depths
        self.own_trades = own_trades
        self.market_trades = market_trades
        self.position = position
        self.observations = observations

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


class ProsperityEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__
