from functools import reduce

import requests
from bs4 import BeautifulSoup

SCHEME = 'https://'
HOSTNAME = 'www.vaccinateri.org'


class SearchResultItem:
    VACCINATIONS_OFFERED_FIELD_NAME = 'Vaccinations offered:'
    AGE_GROUPS_SERVED_FIELD_NAME = 'Age groups served:'
    SERVICES_OFFERED_FIELD_NAME = 'Services offered:'
    ADDITIONAL_INFORMATION_FIELD_NAME = 'Additional Information:'
    CLINIC_HOURS_FIELD_NAME = 'Clinic Hours\n      :'
    APPOINTMENTS_AVAILABLE_FIELD_NAME = 'Appointments Available or Currently Being Booked:'
    SPECIAL_INSTRUCTIONS_FIELD_NAME = 'Special Instructions:'

    def __init__(self, name, address, vaccinations_offered, age_groups_served, services_offered, additional_information,
                 clinic_hours, appointments_available, special_instructions, clinic_id):
        self.name = name
        self.address = address
        self.vaccinations_offered = vaccinations_offered
        self.age_groups_served = age_groups_served
        self.services_offered = services_offered
        self.additional_information = additional_information
        self.clinic_hours = clinic_hours
        self.appointments_available = appointments_available
        self.special_instructions = special_instructions
        self.clinic_id = clinic_id

    @classmethod
    def fromHTML(cls, soup):
        def parseStrongField(required_field_name, soup, as_list=False):
            if soup.strong.text.strip() != required_field_name:
                raise ValueError(
                    f'SearchResultItem could not be parsed correctly: Expected field "{required_field_name}"'
                    f', got field: "{soup.strong.text.strip()}"')
            if as_list:
                return [x for x in [x.strip() for x in soup.strong.next_sibling.split('\n')] if len(x) != 0]
            else:
                return soup.strong.next_sibling.strip()

        top_level_fields = soup.div.findAll('p', recursive=False)
        second_level_fields = top_level_fields[4].findAll('p', recursive=False)

        name = top_level_fields[0].text.strip()
        address = top_level_fields[1].text.strip()
        vaccinations_offered = parseStrongField(cls.VACCINATIONS_OFFERED_FIELD_NAME, top_level_fields[2], as_list=True)
        age_groups_served = parseStrongField(cls.AGE_GROUPS_SERVED_FIELD_NAME, top_level_fields[3])
        services_offered = parseStrongField(cls.SERVICES_OFFERED_FIELD_NAME, second_level_fields[0], as_list=True)
        additional_information = parseStrongField(cls.ADDITIONAL_INFORMATION_FIELD_NAME, second_level_fields[1])
        clinic_hours = parseStrongField(cls.CLINIC_HOURS_FIELD_NAME, second_level_fields[2])
        appointments_available = int(parseStrongField(cls.APPOINTMENTS_AVAILABLE_FIELD_NAME, second_level_fields[3]))
        special_instructions = parseStrongField(cls.SPECIAL_INSTRUCTIONS_FIELD_NAME, top_level_fields[4].div)
        clinic_id_link = top_level_fields[4].a
        try:
            clinic_id = clinic_id_link['href'].split('clinic_id=')[1]
        except TypeError:
            clinic_id = '0'
        return SearchResultItem(name, address, vaccinations_offered, age_groups_served, services_offered,
                                additional_information, clinic_hours, appointments_available, special_instructions,
                                clinic_id)


class Timeslot:
    def __init__(self, timestr, unixtime, available):
        self.timestr = timestr
        self.unixtime = unixtime
        self.available = available

    @classmethod
    def fromHTML(cls, soup):
        time_choice_input = soup.td.input
        unixtime = time_choice_input['value']
        available = not time_choice_input.has_attr('disabled')
        timestr = soup.span.text.strip()
        return Timeslot(timestr, unixtime, available)

class ClinicWithFreeTimeslots(SearchResultItem):
    timeslots = []

    @classmethod
    def fromSearchResultItem(cls, search_result_item):
        return ClinicWithFreeTimeslots(name=search_result_item.name, address=search_result_item.address, vaccinations_offered=search_result_item.vaccinations_offered, age_groups_served=search_result_item.age_groups_served, services_offered=search_result_item.services_offered, additional_information=search_result_item.additional_information, clinic_hours=search_result_item.clinic_hours, appointments_available=search_result_item.appointments_available, special_instructions=search_result_item.special_instructions, clinic_id=search_result_item.clinic_id)


def clinic_search(location='', search_radius='All', venue_search_name_or_venue_name_i_cont='', clinic_date_eq_year='',
                  clinic_date_eq_month='', clinic_data_eq_day='', vaccinations_name_i_cont='', commit='Search'):
    payload = {
        'location': location,
        'search_radius': search_radius,
        'q[venue_search_name_or_venue_name_i_cont]': venue_search_name_or_venue_name_i_cont,
        'clinic_date_eq[year]': clinic_date_eq_year,
        'clinic_date_eq[month]': clinic_date_eq_month,
        'clinic_date_eq[day]': clinic_data_eq_day,
        'q[vaccinations_name_i_cont]': vaccinations_name_i_cont,
        'commit': commit
    }
    r = requests.get(f'{SCHEME}{HOSTNAME}/clinic/search', params=payload)
    soup = BeautifulSoup(r.text, 'html.parser')
    search_results = soup.find('div', {'class': 'main-container'}).findChild('div', {
        'class': ['mt-24', 'border-t', 'border-gray-200']}).findChildren('div', {
        'class': ['md:flex', 'justify-between', '-mx-2', 'md:mx-0', 'px-2', 'md:px-4', 'pt-4', 'pb-4', 'border-b',
                  'border-gray-200']})
    search_result_items = []
    for item in search_results:
        search_result_items.append(SearchResultItem.fromHTML(item))
    return search_result_items


def client_registration(clinic_id):
    payload = {
        'clinic_id': clinic_id
    }
    timeslots = []
    r = requests.get(f'{SCHEME}{HOSTNAME}/client/registration', params=payload, allow_redirects=False)
    if r.status_code == 302 and r.headers['location'] == 'https://www.vaccinateri.org/errors?message=Clinic+does+not+have+any+appointment+slots+available.':
        print(f'clinic_id {clinic_id} has no appointments available')
        return []
    elif r.status_code != 200:
        print(f'Client registration for clinic_id {clinic_id} returned unexpected status code: {r.status_code}')
        return []
    else:
        soup = BeautifulSoup(r.text, 'html.parser')
        appointments_table = soup.find(id='appointments-section').div.table
        appointment_trs = appointments_table.tbody.findAll('tr', recursive=False)
        for appointment_tr in appointment_trs:
            timeslot = Timeslot.fromHTML(appointment_tr)
            if timeslot.available:
                timeslots.append(timeslot)
    return timeslots


if __name__ == '__main__':
    search_result_items = clinic_search()
    clinics_with_appointments_available_according_to_search = [item for item in search_result_items if item.appointments_available > 0]
    total_appointments_available_according_to_search = reduce(lambda x, y: x + y.appointments_available,
                                                              clinics_with_appointments_available_according_to_search, 0)
    clinics_with_free_timeslots = []
    print(
        f'Search says there are a total of {total_appointments_available_according_to_search} appointments available from {len(clinics_with_appointments_available_according_to_search)} different clinics')
    for clinic_with_appointments_available in clinics_with_appointments_available_according_to_search:
        timeslots = client_registration(clinic_with_appointments_available.clinic_id)
        if len(timeslots) > 0:
            clinic_with_free_timeslots = ClinicWithFreeTimeslots.fromSearchResultItem(clinic_with_appointments_available)
            clinic_with_free_timeslots.timeslots.extend(timeslots)
            clinics_with_free_timeslots.append(clinic_with_free_timeslots)

    for clinic_with_free_timeslots in clinics_with_free_timeslots:
        print(f'Clinic {clinic_with_free_timeslots.name} id: {clinic_with_free_timeslots.clinic_id} offers the following free timeslots at {SCHEME}{HOSTNAME}/client/registration?clinic_id={clinic_with_free_timeslots.clinic_id}:')
        for timeslot in clinic_with_free_timeslots.timeslots:
            print(f'    {timeslot.timestr}')

