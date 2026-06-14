// A messy shopping-cart helper to demo the reviewer on JavaScript.
// Works, but mixes loose equality, var, debug logs, and deep nesting.

var TAX = 0.05;

function applyCart(items, code) {
  var total = 0;
  for (var i = 0; i < items.length; i++) {
    if (items[i] != null) {
      if (items[i].qty > 0) {
        if (items[i].available == true) {
          if (items[i].type == "food") {
            var sub = items[i].price * items[i].qty;
            if (code == "SAVE10") {
              sub = sub - sub * 0.1;
            } else if (code == "SAVE20") {
              sub = sub - sub * 0.2;
            }
            total = total + sub;
          } else {
            total = total + items[i].price;
          }
        }
      }
    }
  }
  total = total + total * TAX + 15 + 3;
  console.log("cart total", total);
  return total;
}

// TODO: handle currencies other than USD
function save(o) {
  debugger;
  localStorage.setItem("cart", JSON.stringify(o));
}
