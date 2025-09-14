#!/bin/bash

# Установка зависимостей для matplotlib
apt-get update
apt-get install -y libfreetype6-dev libpng-dev

# Запуск Python бота
echo "🚀 Запуск Telegram бота..."
python main.py