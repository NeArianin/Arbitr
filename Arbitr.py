# Пример простого бота для межбиржевого арбитража
# Основная идея работы бота:
#   Бот осуществляет надзор за ценами на криптовалюты на разных биржах
#   Когда между биржами возникает разница в цене:
#       Бот покупает валюту на бирже, где она стоит дешевле
#       Переводит средства на кошелёк на той бирже, где она стоит дороже
#       После и продаёт данную валюту
#   ( разработка кода шла строго исходя из тестового задания,
#     в дальнейшем будут встречаться предложения по модификации текущего кода
#     такие предложения будут находиться в скобках)

# Библиотеки

#Импортируем библиотеки для работы с временем
import time
from datetime import datetime

#Импортируем библиотеки необходимые для работы с API
import json
import websocket
import requests

#Импорт библиотек необходимых для организации работы на компьютере
import os.path
import threading

#Импорт библиотек приминяемых для визуализации данных
#(в данном случае используется matplotlib ввиду
# наличия в нём комктных способов визуализации в реальном времени,
# в общем случае моё предпочтение для визуализации отдаём plotly.js и dash)
import pandas as pd
import matplotlib.animation as animation
import matplotlib.pyplot as plt


# Создадим класс биржи, где будет храниться информация о текущем балансе на кошельке биржи
# и с помощью которого будет эмулироваться дейсвия внутри биржи
class StockMarket():

#   При инициализации передаём информацию о текущем состоянии биржи с помощью словаря
#   В словаре в качестве ключей выступает название валюты
#   В качестве значений выступает подсловарь хранящий информацию:
#       о текущем количестве единиц валюты на кошельке
#       и цене за единицу валюты на бирже в долларах
#
    def __init__(self, balance = None ):

        self.balance_USD = None
        if (balance):
            self.balance = balance
        else:
#           Пример и простейшая версия словаря с используемыми данными
            self.balance = {'USD': {
                'value': 0,
                'price': 1
            } }

#   Метод для обновление текущего количества единиц валюты на кошельке,
#   будет использован в дальнейшем для эмуляции межбиржевых транзакций
    def update_value(self, value_name, new_value):

        if (value_name in self.balance.keys()):
            self.balance[value_name]['value'] = new_value
        else:
            print('There is no such currency on the exchange')

#   Метод для обновление текущего цены за единицу валюты на кошельке
    def update_price(self, value_name, new_price):

        if (value_name in self.balance.keys()):
            self.balance[value_name]['price'] = new_price
        else:
            print('There is no such currency on the exchange')

#   Метод для эмуляции обмена валют внутри биржи
    def exchange(self, currency_value_name, purchase_value_name, purchase_value_quantity):

        if (self.balance[purchase_value_name]['price'] > 0):
            # Рассчёт затрат исходя из относительной цены в долларах
            expenses = purchase_value_quantity * (self.balance[purchase_value_name]['price']/self.balance[currency_value_name]['price'])
        else:
            print('This currency is worthless or there is no data on durability')
            return

        if (currency_value_name in self.balance.keys()):

            print(self.balance[currency_value_name]['value'])

            if (self.balance[currency_value_name]['value'] >= expenses):
                self.balance[currency_value_name]['value'] = self.balance[currency_value_name]['value'] - expenses
                self.balance[purchase_value_name]['value'] = self.balance[purchase_value_name]['value'] + purchase_value_quantity
            else:
                print('Not enough currency')
        else:
            print('There is no such currency on the exchange')


# Класс арбитра осущевляет эмуляцию работы межбиржевого арбитража
class Arbitr():

#   При инициализации используется два экземляра StockMarket
#   ( класс можно модифицировать отправляя туда лист StockMarcket для работы с большим количеством бирж
#     а так же отправлять туда лист валютынх пар для увеличение количества )
    def __init__(self, stock_market_1, stock_market_2, ):


        self.stock_market_1 =  stock_market_1['stock_market']

        # Формируем REST запрос для первой посылаемой биржей для получение текущих данных о цене
        # (на данный момент поддерживается только один запрос на одну валютную пару,
        # в случае отправки туда листа валютных пар можно в цикле генерировать лист REST запросов)

        self.stock_market_1_request = f"{stock_market_1['url']}/api/v5/market/ticker?instId={stock_market_1['symbol']}"
        self.stock_market_1_name = stock_market_1['name']

        self.stock_market_2 = stock_market_2['stock_market']

        # Формируем сокет для второй биржи для получение текущих данных о цене
        # ( Изначально преполагалось использование сокетов для обеих бирж, но произошла накладка при использовании вебсокета для первой биржи
        #   поэтому было принято решение использовать там REST запрос, что облечает синхронизацию потока данных, но в общем случае не лучшая практика
        #   ,поэтому хорошей идеей будет выбрать один метод и работать с ним, в случае надобности модификация кода не займёт много времени,
        #   придёться несколько методов которые идут дальше)
        self.stock_market_2_socket = f"wss://stream.binance.com:9443/ws/{stock_market_2['symbol']}t@kline_{stock_market_2['interval']}"
        self.stock_market_2_name = stock_market_2['name']
        self.stock_market_2_WebSocket = websocket.WebSocketApp(
                                    self.stock_market_2_socket,
                                    on_open= self.on_open,
                                    on_error= self.on_error,
                                    on_message=self.on_message,
                                    on_close=self.on_close)

        # Название файла в который будет записываться результат работы, формат csv выбран ввиду удобства и гибкости при работе с ним
        self.output_file_name = 'Result.csv'

        # Переменная для фиксации последнего дейсвтия совершённого арбитром
        self.last_action = 'None'

        # Создаём внутри объекты для визуализации процесса торговли
        self.fig, self.ax = plt.subplots(figsize=(15,4), nrows=1, ncols=3)
        # Создаём переменную для запоминания текущего выигрыша от реализации стратегии
        self.current_profit = 0

        pass
    # При открытии сокета пишем, то он открыт
    def on_open(self, msg):
        print('OPEN')

    # При ошибки сокета выводим ошибку
    def on_error(self, error, msg):
        print(msg)
    # При получения сообщения реализуем часть логики работы системы
    def on_message(self, ws, msg):

        # Посылаем REST запрос на получение цены c первой биржи
        stock_market_1_ticker = requests.get(self.stock_market_1_request).json()
        # Парсим сообщение полученное от вебсокета
        stock_market_2_ticker = json.loads(msg)

        # Запоминаем цены в экземлярах класса StockMarcket
        self.stock_market_2.update_price('BTC', float(stock_market_2_ticker['k']['c']))
        self.stock_market_1.update_price('BTC', float(stock_market_1_ticker['data'][0]['last']))

        # Запускаем реализацию стратегии
        self.strategy()
        # Запускаем запись данных в файл
        self.write_to_file()

    # Метод эмулирующий межбирживые транзакции
    def Transfer_value(self, sender, taker, value_name, quantity):

        sender_value = sender.balance[value_name]['value']
        taker_value = taker.balance[value_name]['value']

        if (sender_value >= quantity):
            sender.update_value(value_name, (sender_value - quantity))
            taker.update_value(value_name, (taker_value + quantity))

    # Метод реализубщий запись резултатов в файл
    def write_to_file(self):

        # Проверяем сущетвует ли файл, есил нет, то создаём новый
        # ( было бы хорошим решением, не только проверять файл на существование,
        #    но и проверять его содержимое на соответсви стандартом, а так же
        #    генерировать новые файлы для каждой сессии, но в рамках текущей задачи
        #    это не имеет большого смысла)
        if (not os.path.exists(self.output_file_name)):


            res_file = open(self.output_file_name, 'w')
            res_file.write("datetime," # запоминаем текущее время и дату
                           "action," # запоминаем совершённое действие
                           "sum_usd," # текущую общую сумму долларов
                           "sum_btc," # и общую сумму криптовалюты
                           # а так же эти же данные для каждой биржи отдельно,
                           # вместе с ценами на криптовалюты
                           f"{self.stock_market_1_name}_usd,"
                           f"{self.stock_market_1_name}_btc,"
                           f"{self.stock_market_1_name}_current_price,"
                           f"{self.stock_market_2_name}_usd,"
                           f"{self.stock_market_2_name}_btc,"
                           f"{self.stock_market_2_name}_current_price,"
                           'profit'
                           '\n')
            res_file.flush()
            res_file.close()

        # добавляем результаты работы в файл
        res_file = open(self.output_file_name, 'a')
        new_line = f"{datetime.now()}," \
                   f"{self.last_action}," \
                   f"{self.stock_market_2.balance['USD']['value'] + self.stock_market_1.balance['USD']['value']}," \
                   f"{self.stock_market_2.balance['BTC']['value'] + self.stock_market_1.balance['BTC']['value']}," \
                   f"{self.stock_market_1.balance['USD']['value']}," \
                   f"{self.stock_market_1.balance['BTC']['value']}," \
                   f"{self.stock_market_1.balance['BTC']['price']}," \
                   f"{self.stock_market_2.balance['USD']['value']}," \
                   f"{self.stock_market_2.balance['BTC']['value']}," \
                   f"{self.stock_market_2.balance['BTC']['price']}," \
                   f"{self.current_profit}\n"

        res_file.write(new_line)
        res_file.close()

    # Метод реализующий вывод промежуточных результатов в консоль, использовался для дебага
    # def output_current_data(self):
    #
    #     print(f'{self.stock_market_1_name} USD - ', self.stock_market_1.balance['USD']['value'])
    #     print(f'{self.stock_market_1_name} BTC - ', self.stock_market_1.balance['BTC']['value'])
    #
    #     print(f'{self.stock_market_2_name} USD - ', self.stock_market_2.balance['USD']['value'])
    #     print(f'{self.stock_market_2_name} BTC - ', self.stock_market_2.balance['BTC']['value'])
    #
    #     print('Sum USD - ', self.stock_market_2.balance['USD']['value'] + self.stock_market_1.balance['USD']['value'])
    #     print('Sum BTC - ', self.stock_market_2.balance['BTC']['value'] + self.stock_market_1.balance['BTC']['value'])
    #
    #     print('Profit - ', self.current_profit)
    #     print(f'{self.stock_market_1_name} Price - ', self.stock_market_1.balance['BTC']['price'])
    #     print(f'{self.stock_market_2_name} Price - ', self.stock_market_2.balance['BTC']['price'])

    # Метод реализующий стратегию работы бота
    def strategy(self):

        # Криптовалюты покупаются по константному значению, так было сделано,
        # ввиду адаптивности данного способа под любую реализуемую стратегию
        # ( В целом, имеет смысл реализации более сложной стратегии подбора количества закупаемой валюыт
        #   Например закупать валюты на все имеющиеся средства, но рассчёт данных показателей сильно завист
        #   реальных условиях работы с биржей, так следует учитывать шанс того, что размещение ордера
        #   может быть размещено недостаточно быстро и так далее, в рамках эмуляции такиз условий не сущевует,
        #   а значит эмулируемые стратегии выбора количества все по реалистичности работы будет эквиваленты)
        quantity = 1

        self.last_action = 'none'
        #Запоминаем обущую сумму в долларах для данной валюты до реализации стратегии
        prev_sum = self.stock_market_1.balance['USD']['value'] + self.stock_market_2.balance['USD']['value']

        # Реализуем стратегию описанную в самом начале файла
        if (self.stock_market_2.balance['BTC']['price'] != self.stock_market_1.balance['BTC']['price']):

            if (self.stock_market_2.balance['BTC']['price'] > self.stock_market_1.balance['BTC']['price']):


                self.stock_market_1.exchange('USD','BTC', quantity)

                self.Transfer_value(self.stock_market_1, self.stock_market_2, 'BTC', quantity)
                self.stock_market_2.exchange('BTC', 'USD', quantity * self.stock_market_2.balance['BTC']['price'])


                self.last_action = 'buy_okx_sell_binance'

                pass
            else:

                self.stock_market_2.exchange('USD','BTC', quantity)
                self.Transfer_value(self.stock_market_2, self.stock_market_1, 'BTC', quantity)
                self.stock_market_1.exchange('BTC', 'USD', quantity * self.stock_market_1.balance['BTC']['price'])


                self.last_action = 'buy_stock_market_2_sell_okx'

                pass

            pass

        # Фиксируем прибыль
        current_sum = self.stock_market_1.balance['USD']['value'] + self.stock_market_2.balance['USD']['value']
        self.current_profit = current_sum - prev_sum

    # Фиксируем прибыль
    def on_close(self, ws):
        print('CLOSE')

    # Метод запукска работы бота
    def start(self):

        # Реализацию стратегии работы отправляем в отдельный тред, чтобы можно было в реальном времени визуализировать данные
        t1 = threading.Thread(target=self.stock_market_2_WebSocket.run_forever)
        t1.start()

        # Ожидаем пока не создаться файл с данными
        time.sleep(10)

        # Запускаем визуализацию в реальном времени
        ani = animation.FuncAnimation(self.fig, self.Vizual, interval=1000)
        plt.show()

    # Метод реализующий визуализацию данных
    def Vizual(self, i):

        #Получаем данные из файла, в который мы сохраняем результаты работы
        data = pd.read_csv(self.output_file_name)

        # Создаём общую временную шкалу для всех графиков
        x = range(0, len(data[f'{self.stock_market_2_name}_current_price'].values))

        # Создаём график движение цены на первой бирже
        y = data[f'{self.stock_market_2_name}_current_price'].values
        self.ax[0].clear()
        self.ax[0].plot(x,y)
        self.ax[0].set_title(f'{self.stock_market_2_name}_price')

        # Создаём график движение цены на второй бирже
        y = data[f'{self.stock_market_1_name}_current_price'].values
        self.ax[1].clear()
        self.ax[1].plot(x,y)
        self.ax[1].set_title(f'{self.stock_market_2_name}_price')

        # Создаём график отображающий динамику изменние профита во времени
        y = data['profit'].values
        self.ax[2].clear()
        self.ax[2].plot(x,y)
        self.ax[2].set_title('Profit')

        pass

# Функция для тестирования работы
def main():

    #Создаём условия для первой биржи
    stock_marcket_1 = {
        'name': 'Okex',
        'url': 'https://www.okex.com',
        'symbol': 'BTC-USDT',
        'stock_market': StockMarket(
            {
                'USD': {
                    'value': 200000,
                    'price': 1
                },
                'BTC': {
                    'value': 0,
                    'price': 0
                }
            }
        )
    }

    # Создаём условия для второй биржи
    stock_marcket_2 = {
        'name': 'Binance',
        'interval': '1m',
        'symbol': 'btcusd',
        'stock_market': StockMarket(
            {
                'USD': {
                    'value': 500000,
                    'price': 1
                },
                'BTC': {
                    'value': 0,
                    'price': 0
                }
            }
        )
    }

    # Создаём арбитра
    arbitr = Arbitr(stock_marcket_1, stock_marcket_2)
    # Начинаем его работы
    arbitr.start()
# Запускаем
if __name__ == "__main__":
    main()