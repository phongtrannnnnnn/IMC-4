# Tutorial Round - "Simulator Practice"

> Source: https://imc-prosperity.notion.site/tutorial-round-simulator-practice

## Overview

You are on your way to **Intara**, a distant planet that has reached out for help. Before you arrive, you can use the trading simulator from within your spacecraft. Trading options might be limited, but it gives you the opportunity to experiment with some initial tradable goods, run your first bits of Python code, and get familiar with the Graphical User Interface.

You can test your Python program as many times as you like and receive (almost) instant feedback on its performance. Make the most of your time in the simulator, because once you land on Intara, the time to practice is over and your real mission begins.

This tutorial round lasts until **April 14**, when your first official round begins.

## Round Objective

Write your first Python program to trade **Emeralds** and **Tomatoes**, upload it to the trading simulator to test its performance, and become familiar with the Graphical User Interface and core controls of Prosperity 4.

## Algorithmic Trading Challenge: "Simulator Practice"

The **Emeralds** are precious gemstones with quite a stable value, while the value of **Tomatoes** tends to fluctuate over time. They both have position limits, i.e., a maximum number you can hold at any point in time.

### Products & Position Limits

| Product | Position Limit | Behavior |
|---------|---------------|----------|
| `EMERALDS` | **80** | Precious gemstones with a **stable value** |
| `TOMATOES` | **80** | Value **fluctuates over time** |

> See also: [Position Limits](https://imc-prosperity.notion.site/writing-an-algorithm-in-python#328e8453a09380cfb53edaa112e960a9) for extra context and troubleshooting.

## Manual Trading

**N/A** — Manual trading is inactive during the tutorial round. It activates starting from Round 1.

## On-Board Advisors

You can choose **one out of three** available Advisors during the Tutorial Round. You may switch Advisors for as long as the Tutorial Round lasts. As soon as the Tutorial Round ends, your selection will be locked in and you can no longer switch On-Board advisors.

From the start of Round 1 onwards, these On-Board Advisors will provide interesting perspectives on the challenges that you'll face and provide guidance to help you make your mission a success.

## Key Notes

- The tutorial round does **not** count toward your final leaderboard score
- You can submit as many algorithm versions as you'd like
- Use the logs and dashboard to debug and improve your algorithm
- `traderData` can be used to persist state between iterations
- The file must be named `trader.py` and contain a `Trader` class
