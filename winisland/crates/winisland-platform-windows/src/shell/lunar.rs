use windows::Globalization::{Calendar, CalendarIdentifiers};
use winisland_platform::LunarDate;

pub(super) fn convert(year: u16, month: u16, day: u16) -> Option<LunarDate> {
    let calendar = Calendar::new().ok()?;
    calendar
        .ChangeCalendarSystem(&CalendarIdentifiers::Gregorian().ok()?)
        .ok()?;
    calendar.SetYear(i32::from(year)).ok()?;
    calendar.SetMonth(1).ok()?;
    calendar.SetDay(1).ok()?;
    calendar.SetMonth(i32::from(month)).ok()?;
    calendar.SetDay(i32::from(day)).ok()?;
    calendar
        .ChangeCalendarSystem(&CalendarIdentifiers::ChineseLunar().ok()?)
        .ok()?;
    let numeric = calendar.MonthAsNumericString().ok()?.to_string();
    let leap = numeric.ends_with('*');
    let month = numeric.trim_end_matches('*').parse().ok()?;
    let day = u8::try_from(calendar.Day().ok()?).ok()?;
    Some(LunarDate { month, day, leap })
}
