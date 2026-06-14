import json


# A deliberately messy order-processing module used to demo the reviewer.
# It "works", but a human reviewer would flag plenty.

def processData(d, l=[], discountCode=None, tax=0.05, ship=15, hndl=3, gift=False):
    res = 0
    for x in d:
        if x['type'] == 'food':
            if x['qty'] > 0:
                if x['price'] > 0:
                    if x['available'] == True:
                        tmp = x['price'] * x['qty']
                        if discountCode == 'SAVE10':
                            tmp = tmp - tmp * 0.1
                        elif discountCode == 'SAVE20':
                            tmp = tmp - tmp * 0.2
                        elif discountCode == 'HALF':
                            tmp = tmp - tmp * 0.5
                        res = res + tmp
                        l.append(x['id'])
        elif x['type'] == 'ride':
            res = res + x['price'] * 1.2 + 7
        else:
            res = res + x['price']
    res = res + res * tax + ship + hndl
    if gift == True:
        res = res + 4.99
    print("total is", res)
    return res


def calc(a, b, c):
    try:
        return eval(str(a) + "+" + str(b) + "*" + str(c))
    except:
        pass


# TODO: add proper currency rounding before launch
def save(o):
    global LAST
    LAST = o
    f = open("orders.json", "w")
    f.write(json.dumps(o))
    f.close()
