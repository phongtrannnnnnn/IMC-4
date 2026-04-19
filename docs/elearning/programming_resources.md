# Programming Resources

> Source: https://imc-prosperity.notion.site/programming-resources

## Overview

To participate in algorithmic trading you will need to have some programming skills. Python programming, specifically. Here you will find some resources that will help you get started.

## Python Basics

If you're new to Python, these resources will help you learn the fundamentals:

### Online Tutorials
- **Python.org Official Tutorial**: https://docs.python.org/3/tutorial/
- **Codecademy Python Course**: Interactive, beginner-friendly
- **Real Python**: In-depth tutorials and articles

### Key Python Concepts for Prosperity
- **Data Structures**: Lists, dictionaries, sets, tuples
- **Control Flow**: if/else, for loops, while loops
- **Functions and Classes**: Defining and using classes (your `Trader` class)
- **String Manipulation**: For `traderData` serialization
- **Exception Handling**: try/except blocks for robust code

## Libraries Available

The following libraries are available in the Prosperity environment (**Python 3.10**):

| Library | Version | Use Case |
|---------|---------|----------|
| `pandas` | 1.5.3 | Data manipulation and analysis |
| `numpy` | 1.24.2 | Numerical computing, arrays, math functions |
| `statistics` | stdlib | Statistical functions (mean, stdev, etc.) |
| `math` | stdlib | Mathematical functions |
| `typing` | stdlib | Type hints |
| `jsonpickle` | 3.0.1 | Serialization of complex objects for `traderData` |

> ⚠️ **No other libraries are supported.** Any attempt to use unsupported libraries or access external data/APIs will result in disqualification.

## Tips for Prosperity

### Efficient Code
- Your `run()` method must complete within **900ms**
- Avoid heavy computation in each iteration
- Pre-compute values where possible
- Use vectorized NumPy/pandas operations over Python loops

### State Management
- Use `traderData` to persist state between iterations
- Serialize with `json.dumps()` or `jsonpickle.encode()`
- Keep serialized state compact
- AWS Lambda is stateless — do **not** rely on class/global variables persisting between calls

### Debugging
- Use `print()` statements to log data during simulation
- Check the logs in the Mission Control dashboard after submitting
- Test with different market conditions

### File Requirements
- File must be named **`trader.py`**
- Must contain a class named **`Trader`**
- The `Trader` class must have a **`run(self, state: TradingState)`** method
- Returns a tuple: `(result, conversions, traderData)`
