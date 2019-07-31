from vnpy.trader.object import TradeData, OrderData, TickData
from vnpy.trader.engine import BaseEngine
from vnpy.app.algo_trading import AlgoTemplate
from vnpy.trader.event import EVENT_LOGIN
from vnpy.trader.constant import (Direction, Offset, OrderType)
from datetime import datetime


class ArbitrageAlgo(AlgoTemplate):
    """"""

    display_name = "Arbitrage 套利"

    default_setting = {
        "active_vt_symbol": "",
        "passive_vt_symbol": "",
        # "spread_up": 0.0,
        # "spread_down": 0.0,
        # "max_pos": 0,
        # "min_pos": 0,
        "hedge_num": 0,
        "level_pre": 0.01,
        "level_gap": 0.002,
        "level_num": 10,
        "slippage": 0.01,
        "interval": 0
    }

    variables = [
        "timer_count",
        "active_vt_orderid",
        "passive_vt_orderid",
        "active_pos",
        "passive_pos"
    ]

    def __init__(
            self,
            algo_engine: BaseEngine,
            algo_name: str,
            setting: dict
    ):
        """"""
        super().__init__(algo_engine, algo_name, setting)

        # Parameters
        self.active_vt_symbol = setting["active_vt_symbol"]
        self.passive_vt_symbol = setting["passive_vt_symbol"]
        self.interval = setting["interval"]
        self.hedge_num = setting["hedge_num"]
        self.level_pre = setting["level_pre"]
        self.level_gap = setting["level_gap"]
        self.level_num = setting["level_num"]
        self.slippage = setting["slippage"]

        # Variables
        self.active_vt_orderid = ""
        self.passive_vt_orderid = ""
        self.active_pos = 0
        self.passive_pos = 0
        self.timer_count = 0
        self.last_price = 0
        self.active_tick = None
        self.passive_tick = None

        self.subscribe(self.active_vt_symbol)
        self.subscribe(self.passive_vt_symbol)

        self.put_parameters_event()
        self.put_variables_event()

        self.init_holding()
        self.algo_engine.main_engine.event_engine.register(EVENT_LOGIN, self.on_login)

    def on_login(self, event):
        self.write_log("重连行情，订阅symbol")
        self.subscribe(self.active_vt_symbol)
        self.subscribe(self.passive_vt_symbol)

    def init_holding(self):
        # 查询初始持仓
        active_holding_long = self.get_position(f"{self.active_vt_symbol}.{Direction.LONG}")
        active_holding_short = self.get_position(f"{self.active_vt_symbol}.{Direction.SHORT}")
        passive_holding_long = self.get_position(f"{self.passive_vt_symbol}.{Direction.LONG}")
        passive_holding_short = self.get_position(f"{self.passive_vt_symbol}.{Direction.SHORT}")
        self.active_pos = (float(active_holding_long.volume) if active_holding_long else 0) - (
            float(active_holding_short.volume) if active_holding_short else 0)
        self.passive_pos = (float(passive_holding_long.volume) if passive_holding_long else 0) - (
            float(passive_holding_short.volume) if passive_holding_short else 0)

    def on_stop(self):
        """"""
        self.write_log("停止算法")

    def on_start(self):
        self.init_holding()

    def on_order(self, order: OrderData):
        """"""
        if order.vt_symbol == self.active_vt_symbol:
            if not order.is_active():
                self.active_vt_orderid = ""
        elif order.vt_symbol == self.passive_vt_symbol:
            if not order.is_active():
                self.passive_vt_orderid = ""
        self.put_variables_event()

    def on_trade(self, trade: TradeData):
        """"""
        # Update pos
        if trade.direction == Direction.LONG:
            if trade.vt_symbol == self.active_vt_symbol:
                self.active_pos += trade.volume
            else:
                self.passive_pos += trade.volume
        else:
            if trade.vt_symbol == self.active_vt_symbol:
                self.active_pos -= trade.volume
            else:
                self.passive_pos -= trade.volume

        self.put_variables_event()

    def on_tick(self, tick: TickData):
        if tick.vt_symbol == self.active_vt_symbol:
            self.active_tick = tick
        elif tick.vt_symbol == self.passive_vt_symbol:
            self.passive_tick = tick
        if self.active_tick is None or self.passive_tick is None or \
                not self.active_tick.last_price or not self.passive_tick.last_price\
                or not self.active_tick.bid_price_1 or not self.active_tick.ask_price_1\
                or not self.passive_tick.ask_price_1 or not self.passive_tick.bid_price_1:
            self.write_log("获取某条套利腿的行情失败，无法交易")
            return

        # Cancel all active orders before moving on
        if self.active_vt_orderid or self.passive_vt_orderid:
            # self.write_log("有未成交委托，等待成交")
            # self.cancel_all()
            return

        # Make sure that active leg is fully hedged by passive leg
        if (self.active_pos + self.passive_pos) != (0 - self.hedge_num):
            self.write_log("主动腿和被动腿数量不一致，执行对冲")
            self.hedge()
            return
        # return
        # 升水价差
        if float(self.active_tick.bid_price_1) > float(self.passive_tick.ask_price_1):
            # 有贴水仓位先平仓
            if self.passive_pos < 0:
                volume = abs(self.passive_pos)
                # 主动腿平多
                self.active_vt_orderid = self.sell(
                    self.active_vt_symbol,
                    float(self.active_tick.bid_price_1) * (1 - self.slippage),
                    volume
                )
                # 被动腿平空
                self.passive_vt_orderid = self.cover(
                    self.passive_vt_symbol,
                    float(self.passive_tick.ask_price_1) * (1 + self.slippage),
                    volume
                )
            else:
                spread_bid_price = float(self.active_tick.bid_price_1) - float(self.passive_tick.ask_price_1)
                spread_ask_price = float(self.active_tick.ask_price_1) - float(self.passive_tick.bid_price_1)

                spread_bid_volume = min(int(self.active_tick.bid_volume_1),
                                        int(self.passive_tick.ask_volume_1))
                spread_ask_volume = min(int(self.active_tick.ask_volume_1),
                                        int(self.passive_tick.bid_volume_1))
                self.last_price = float(self.active_tick.last_price)
                spread_bid_rate = spread_bid_price / self.last_price
                bid_holding = int((spread_bid_rate - self.level_pre) / self.level_gap) * self.level_num
                spread_ask_rate = spread_ask_price / self.last_price
                ask_holding = max(int((spread_ask_rate - self.level_pre) / self.level_gap + 1) * self.level_num, 0)

                msg = f"升水价差盘口，时间：{tick.datetime}， 主动腿last:{self.last_price}，被动腿last:{self.passive_tick.last_price}，\n" \
                    f"主动腿bid1:{self.active_tick.bid_price_1}，被动腿ask1:{self.passive_tick.ask_price_1}；主动腿ask1：{self.active_tick.ask_price_1}，被动腿bid1：{self.passive_tick.bid_price_1}，\n" \
                    f"开：价差{round(spread_bid_price, 4)}，价差比{round(spread_bid_rate, 5)}，最小空单应为{bid_holding}张，\n" \
                    f"平：价差{round(spread_ask_price, 4)}，价差比{round(spread_ask_rate, 5)}，最大空单应为{ask_holding}张"

                if bid_holding > abs(self.active_pos + self.hedge_num):
                    volume = min(float(spread_bid_volume),
                                 float(bid_holding - abs(self.active_pos + self.hedge_num)))
                    self.write_log(msg)
                    self.write_log(f"当前主动腿有空单{self.active_pos}张，对冲单{self.hedge_num}张，还应再开{volume}张空单")
                    if self.active_vt_symbol.endswith('.OKEX'):
                        # 主动腿开空
                        self.active_vt_orderid = self.short(
                            self.active_vt_symbol,
                            float(self.active_tick.bid_price_1) * (1 - self.slippage),
                            volume,
                            offset=Offset.OPEN
                        )
                        # 被动腿开多
                        self.passive_vt_orderid = self.buy(
                            self.passive_vt_symbol,
                            float(self.passive_tick.ask_price_1) * (1 + self.slippage),
                            volume
                        )
                    elif self.active_vt_symbol.endswith('.HUOBI'):
                        active_order = {
                            'vt_symbol': self.active_vt_symbol,
                            'direction': Direction.SHORT,
                            'price': float(self.active_tick.bid_price_1),
                            'volume': volume,
                            'order_type': OrderType.OPTIMAL,
                            'offset': Offset.OPEN
                        }
                        passive_order = {
                            'vt_symbol': self.passive_vt_symbol,
                            'direction': Direction.LONG,
                            'price': float(self.active_tick.bid_price_1),
                            'volume': volume,
                            'order_type': OrderType.OPTIMAL,
                            'offset': Offset.OPEN
                        }
                        [self.active_vt_orderid, self.passive_vt_orderid] = self.send_orders([active_order, passive_order])

                if ask_holding < abs(self.active_pos + self.hedge_num):
                    volume = min(float(spread_ask_volume),
                                 float(abs(self.active_pos + self.hedge_num)) - ask_holding)
                    self.write_log(msg)
                    self.write_log(f"当前主动腿有空单{self.active_pos}张，对冲单{self.hedge_num}张，还应再平{volume}张空单")
                    if self.active_vt_symbol.endswith('.OKEX'):
                        # 主动腿平空
                        self.active_vt_orderid = self.cover(
                            self.active_vt_symbol,
                            float(self.active_tick.ask_price_1) * (1 + self.slippage),
                            volume
                        )
                        # 被动腿平多
                        self.passive_vt_orderid = self.sell(
                            self.passive_vt_symbol,
                            float(self.passive_tick.bid_price_1) * (1 - self.slippage),
                            volume
                        )
        # 贴水行情
        elif float(self.passive_tick.bid_price_1) > float(self.active_tick.ask_price_1):
            # 有升水仓位先平仓
            if self.passive_pos > 0:
                volume = self.passive_pos
                # 主动腿平空
                self.active_vt_orderid = self.cover(
                    self.active_vt_symbol,
                    float(self.active_tick.ask_price_1) * (1 + self.slippage),
                    volume
                )
                # 被动腿平多
                self.passive_vt_orderid = self.sell(
                    self.passive_vt_symbol,
                    float(self.passive_tick.bid_price_1) * (1 - self.slippage),
                    volume
                )
            else:
                spread_bid_price = float(self.passive_tick.bid_price_1) - float(self.active_tick.ask_price_1)
                spread_ask_price = float(self.passive_tick.ask_price_1) - float(self.active_tick.bid_price_1)

                spread_bid_volume = min(int(self.passive_tick.bid_volume_1),
                                        int(self.active_tick.ask_volume_1))
                spread_ask_volume = min(int(self.passive_tick.ask_volume_1),
                                        int(self.active_tick.bid_volume_1))
                self.last_price = float(self.passive_tick.last_price)
                spread_bid_rate = spread_bid_price / self.last_price
                bid_holding = int((spread_bid_rate - self.level_pre) / self.level_gap) * self.level_num
                spread_ask_rate = spread_ask_price / self.last_price
                ask_holding = max(int((spread_ask_rate - self.level_pre) / self.level_gap + 1) * self.level_num, 0)
                msg = f"贴水价差盘口，时间：{tick.datetime}， 主动腿last:{self.active_tick.last_price}，被动腿last:{self.passive_tick.last_price}，\n" \
                    f"主动腿bid1:{self.active_tick.bid_price_1}，被动腿ask1:{self.passive_tick.ask_price_1}；主动腿ask1：{self.active_tick.ask_price_1}，被动腿bid1：{self.passive_tick.bid_price_1}，\n" \
                    f"开：价差{round(spread_bid_price, 4)}，价差比{round(spread_bid_rate, 5)}，最小空单应为{bid_holding}张，\n" \
                    f"平：价差{round(spread_ask_price, 4)}，价差比{round(spread_ask_rate, 5)}，最大空单应为{ask_holding}张"

                if bid_holding > abs(self.passive_pos):
                    volume = min(float(spread_bid_volume),
                                 float(bid_holding - abs(self.passive_pos)))
                    self.write_log(msg)
                    self.write_log(f"当前主动腿有空单{self.active_pos}张，对冲单{self.hedge_num}张，还应再开{volume}张空单")

                    # 被动腿开空
                    self.passive_vt_orderid = self.short(
                        self.passive_vt_symbol,
                        float(self.passive_tick.bid_price_1) * (1 - self.slippage),
                        volume,
                        offset=Offset.OPEN
                    )
                    # 主动腿开多
                    self.active_vt_orderid = self.buy(
                        self.active_vt_symbol,
                        float(self.active_tick.ask_price_1) * (1 + self.slippage),
                        volume,
                        offset=Offset.OPEN
                    )
                if ask_holding < abs(self.passive_pos):
                    volume = min(float(spread_ask_volume),
                                 float(abs(self.passive_pos)) - ask_holding)
                    self.write_log(msg)
                    self.write_log(f"当前主动腿有空单{self.active_pos}张，对冲单{self.hedge_num}张，还应再平{volume}张空单")

                    # 被动腿平空
                    self.passive_vt_orderid = self.cover(
                        self.passive_vt_symbol,
                        float(self.passive_tick.ask_price_1) * (1 + self.slippage),
                        volume
                    )
                    # 主动腿平多
                    self.active_vt_orderid = self.sell(
                        self.active_vt_symbol,
                        float(self.active_tick.bid_price_1) * (1 - self.slippage),
                        volume
                    )
        # Update GUI
        self.put_variables_event()

    def on_timer(self):
        """"""
        self.timer_count += 1
        if self.timer_count < self.interval:
            return
        self.timer_count = 0

        currency_time = datetime.now()
        if currency_time>self.active_tick.datetime:
            active_tick_time_delay = (currency_time - self.active_tick.datetime).seconds
        else:
            active_tick_time_delay = (self.active_tick.datetime - currency_time).seconds
        if currency_time > self.passive_tick.datetime:
            passive_tick_time_delay = (currency_time - self.passive_tick.datetime).seconds
        else:
            passive_tick_time_delay = (self.passive_tick.datetime - currency_time).seconds

        if active_tick_time_delay > 10 or passive_tick_time_delay > 10:
            self.send_email('tick数据行情异常断开',f'{self.active_vt_symbol}，{self.passive_vt_symbol} tick 数据异常')
            self.interval = 60*30

    def hedge(self):
        """"""
        # 对冲单从主动腿下
        volume = self.active_pos + self.passive_pos + self.hedge_num
        # 对冲单数量少了，主动腿开空
        if volume > 0:
            self.active_vt_orderid = self.short(
                self.active_vt_symbol,
                float(self.active_tick.bid_price_1) * (1 - self.slippage),
                volume,
                offset=Offset.OPEN
            )
        # 对冲单数量多了
        elif volume < 0:
            if self.active_pos < volume:
                # 主动腿平空
                self.active_vt_orderid = self.cover(
                    self.active_vt_symbol,
                    float(self.active_tick.ask_price_1) * (1 + self.slippage),
                    abs(volume)
                )
            elif self.passive_pos < volume:
                # 被动腿平空
                self.passive_vt_orderid = self.cover(
                    self.passive_vt_symbol,
                    float(self.passive_tick.ask_price_1) * (1 + self.slippage),
                    abs(volume)
                )
