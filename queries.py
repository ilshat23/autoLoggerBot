CREATE_USER = """
INSERT INTO users (
    telegram_id,
    username
    )
    VALUES (?, ?);
"""

ADD_NEW_CAR = """INSERT INTO user_cars (telegram_id, car_name) VALUES(?, ?);"""

UPDATE_CAR_NAME = """
UPDATE user_cars SET car_name = ? WHERE telegram_id = ? AND car_name = ?;
"""

DELETE_CAR = """
DELETE FROM user_cars WHERE telegram_id = ? and car_name = ?;
"""

CLEAR_CAR_HISTORY = """DELETE FROM repair_history WHERE telegram_id = ?;"""

INSERT_REPAIR_DATA = """
INSERT INTO car_repair_history (
    car_id, repair_date, repair_description, mileage
)
VALUES (
    (SELECT car_id
    FROM user_cars
    WHERE telegram_id = ? AND car_name = ?), ?, ?, ?
);
"""
GET_USER = """
SELECT telegram_id FROM users WHERE telegram_id = ?;
"""

GET_USER_CARS = """
SELECT car_name FROM user_cars WHERE telegram_id = ?;
"""

GET_REPAIR_INFO = """
SELECT mileage, repair_date, repair_description
FROM car_repair_history
WHERE car_id = (
    SELECT car_id FROM user_cars WHERE car_name = ? AND telegram_id = ?
);
"""
