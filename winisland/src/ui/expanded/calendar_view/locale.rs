use winisland_platform::LunarDate;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(super) enum Region {
    UnitedStates,
    China,
    Spain,
}

pub(super) struct Holiday {
    pub(super) day: u16,
    pub(super) name: &'static str,
}

const EN_MONTHS: [&str; 12] = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];
const ES_MONTHS: [&str; 12] = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
];
const EN_WEEKDAYS: [&str; 7] = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
];
const ES_WEEKDAYS: [&str; 7] = [
    "domingo",
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
];
const ZH_WEEKDAYS: [&str; 7] = [
    "星期日",
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
];
const EN_INITIALS: [&str; 7] = ["S", "M", "T", "W", "T", "F", "S"];
const ES_INITIALS: [&str; 7] = ["D", "L", "M", "X", "J", "V", "S"];
const ZH_INITIALS: [&str; 7] = ["日", "一", "二", "三", "四", "五", "六"];

impl Region {
    pub(super) fn from_lang(lang: &str) -> Self {
        let lang = lang.to_ascii_lowercase();
        if lang.starts_with("zh") {
            Self::China
        } else if lang.starts_with("es") {
            Self::Spain
        } else {
            Self::UnitedStates
        }
    }

    pub(super) fn week_start(self) -> u16 {
        match self {
            Self::UnitedStates => 0,
            Self::China | Self::Spain => 1,
        }
    }

    pub(super) fn weekday_name(self, weekday: u16) -> String {
        let index = usize::from(weekday % 7);
        match self {
            Self::UnitedStates => EN_WEEKDAYS[index].to_uppercase(),
            Self::Spain => ES_WEEKDAYS[index].to_uppercase(),
            Self::China => ZH_WEEKDAYS[index].to_string(),
        }
    }

    pub(super) fn weekday_initial(self, weekday: u16) -> &'static str {
        let index = usize::from(weekday % 7);
        match self {
            Self::UnitedStates => EN_INITIALS[index],
            Self::Spain => ES_INITIALS[index],
            Self::China => ZH_INITIALS[index],
        }
    }

    pub(super) fn month_title(self, year: u16, month: u16) -> String {
        let index = usize::from(month.clamp(1, 12) - 1);
        match self {
            Self::UnitedStates => format!("{} {year}", EN_MONTHS[index]),
            Self::Spain => format!("{} {year}", ES_MONTHS[index]),
            Self::China => format!("{year}年{month}月"),
        }
    }

    pub(super) fn short_date(self, month: u16, day: u16) -> String {
        match self {
            Self::UnitedStates => format!("{month}/{day}"),
            Self::Spain => format!("{day}/{month}"),
            Self::China => format!("{month}月{day}日"),
        }
    }

    pub(super) fn holidays(
        self,
        year: u16,
        month: u16,
        lunar: impl Fn(u16, u16, u16) -> Option<LunarDate>,
    ) -> Vec<Holiday> {
        let mut holidays = Vec::new();
        let mut add = |day: u16, name: &'static str| holidays.push(Holiday { day, name });
        match self {
            Self::UnitedStates => {
                for (m, d, name) in [
                    (1, 1, "New Year's Day"),
                    (2, 14, "Valentine's Day"),
                    (6, 19, "Juneteenth"),
                    (7, 4, "Independence Day"),
                    (10, 31, "Halloween"),
                    (11, 11, "Veterans Day"),
                    (12, 24, "Christmas Eve"),
                    (12, 25, "Christmas Day"),
                    (12, 31, "New Year's Eve"),
                ] {
                    if m == month {
                        add(d, name);
                    }
                }
                match month {
                    1 => add(nth_weekday(year, 1, 1, 3), "Martin Luther King Jr. Day"),
                    2 => add(nth_weekday(year, 2, 1, 3), "Presidents' Day"),
                    5 => {
                        add(nth_weekday(year, 5, 0, 2), "Mother's Day");
                        add(last_weekday(year, 5, 1), "Memorial Day");
                    }
                    6 => add(nth_weekday(year, 6, 0, 3), "Father's Day"),
                    9 => add(nth_weekday(year, 9, 1, 1), "Labor Day"),
                    10 => add(nth_weekday(year, 10, 1, 2), "Columbus Day"),
                    11 => add(nth_weekday(year, 11, 4, 4), "Thanksgiving"),
                    _ => {}
                }
                let (easter_month, easter_day) = easter_sunday(year);
                if easter_month == month {
                    add(easter_day, "Easter");
                }
            }
            Self::Spain => {
                for (m, d, name) in [
                    (1, 1, "Año Nuevo"),
                    (1, 6, "Epifanía del Señor"),
                    (5, 1, "Fiesta del Trabajo"),
                    (8, 15, "Asunción de la Virgen"),
                    (10, 12, "Fiesta Nacional de España"),
                    (11, 1, "Todos los Santos"),
                    (12, 6, "Día de la Constitución"),
                    (12, 8, "Inmaculada Concepción"),
                    (12, 25, "Navidad"),
                ] {
                    if m == month {
                        add(d, name);
                    }
                }
                let (good_friday_month, good_friday_day) = good_friday(year);
                if good_friday_month == month {
                    add(good_friday_day, "Viernes Santo");
                }
            }
            Self::China => {
                for (m, d, name) in [
                    (1, 1, "元旦"),
                    (3, 8, "妇女节"),
                    (5, 1, "劳动节"),
                    (5, 4, "青年节"),
                    (6, 1, "儿童节"),
                    (9, 10, "教师节"),
                    (10, 1, "国庆节"),
                ] {
                    if m == month {
                        add(d, name);
                    }
                }
                if month == 4 {
                    add(qingming_day(year), "清明节");
                }
                let days = days_in_month(year, month);
                let (next_year, next_month) = if month == 12 {
                    (year + 1, 1)
                } else {
                    (year, month + 1)
                };
                let lunar_days: Vec<Option<LunarDate>> = (1..=days)
                    .map(|day| lunar(year, month, day))
                    .chain(std::iter::once(lunar(next_year, next_month, 1)))
                    .collect();
                for day in 1..=days {
                    let Some(date) = lunar_days[usize::from(day - 1)] else {
                        continue;
                    };
                    let next = lunar_days[usize::from(day)];
                    if next.is_some_and(|next| !next.leap && next.month == 1 && next.day == 1) {
                        add(day, "除夕");
                    }
                    if date.leap {
                        continue;
                    }
                    match (date.month, date.day) {
                        (1, 1) => add(day, "春节"),
                        (1, 15) => add(day, "元宵节"),
                        (5, 5) => add(day, "端午节"),
                        (7, 7) => add(day, "七夕节"),
                        (8, 15) => add(day, "中秋节"),
                        (9, 9) => add(day, "重阳节"),
                        (12, 8) => add(day, "腊八节"),
                        _ => {}
                    }
                }
            }
        }
        holidays.sort_by_key(|holiday| holiday.day);
        holidays
    }
}

pub(super) fn days_in_month(year: u16, month: u16) -> u16 {
    match month {
        4 | 6 | 9 | 11 => 30,
        2 if (year.is_multiple_of(4) && !year.is_multiple_of(100)) || year.is_multiple_of(400) => {
            29
        }
        2 => 28,
        _ => 31,
    }
}

pub(super) fn weekday(year: u16, month: u16, day: u16) -> u16 {
    const OFFSETS: [i32; 12] = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4];
    let mut year = i32::from(year);
    if month < 3 {
        year -= 1;
    }
    let value = year + year / 4 - year / 100
        + year / 400
        + OFFSETS[usize::from(month.clamp(1, 12) - 1)]
        + i32::from(day);
    value.rem_euclid(7) as u16
}

fn nth_weekday(year: u16, month: u16, target: u16, nth: u16) -> u16 {
    let first = weekday(year, month, 1);
    1 + (target + 7 - first) % 7 + 7 * (nth - 1)
}

fn last_weekday(year: u16, month: u16, target: u16) -> u16 {
    let last = days_in_month(year, month);
    last - (weekday(year, month, last) + 7 - target) % 7
}

fn easter_sunday(year: u16) -> (u16, u16) {
    let y = i32::from(year);
    let a = y % 19;
    let b = y / 100;
    let c = y % 100;
    let d = b / 4;
    let e = b % 4;
    let f = (b + 8) / 25;
    let g = (b - f + 1) / 3;
    let h = (19 * a + b - d - g + 15) % 30;
    let i = c / 4;
    let k = c % 4;
    let l = (32 + 2 * e + 2 * i - h - k) % 7;
    let m = (a + 11 * h + 22 * l) / 451;
    let month = (h + l - 7 * m + 114) / 31;
    let day = (h + l - 7 * m + 114) % 31 + 1;
    (month as u16, day as u16)
}

fn good_friday(year: u16) -> (u16, u16) {
    let (month, day) = easter_sunday(year);
    if day > 2 {
        (month, day - 2)
    } else {
        (month - 1, days_in_month(year, month - 1) + day - 2)
    }
}

fn qingming_day(year: u16) -> u16 {
    let y = f32::from(year % 100);
    ((y * 0.2422 + 4.81).floor() - (y / 4.0).floor()) as u16
}
