import sys
import time
from copy import deepcopy
from functools import reduce

import requests
from bs4 import BeautifulSoup

SCHEME = 'https://'
HOSTNAME = 'www.vaccinateri.org'
INTERVAL = 30
PUSHOVER_USER_KEY = ''
PUSHOVER_API_KEY = ''

LOGO = r'''
                        _             __          ____  ____
 _   ______ ___________(_)___  ____ _/ /____     / __ \/  _/
| | / / __ `/ ___/ ___/ / __ \/ __ `/ __/ _ \   / /_/ // /  
| |/ / /_/ / /__/ /__/ / / / / /_/ / /_/  __/  / _, _// /   
|___/\__,_/\___/\___/_/_/ /_/\__,_/\__/\___/  /_/ |_/___/   
                                                            
                __              __            
          _____/ /_  ___  _____/ /_____  _____
         / ___/ __ \/ _ \/ ___/ //_/ _ \/ ___/
        / /__/ / / /  __/ /__/ ,< /  __/ /    
        \___/_/ /_/\___/\___/_/|_|\___/_/     
                                      
                                       |
                 ,------------=--------|___________|
-=============%%%|         |  |______|_|___________|
                 | | | | | | ||| | | | |___________|
                 `------------=--------|           |
                                       |
                                                                
'''


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
    def from_html(cls, soup):
        def parse_strong_field(required_field_name, soup_, as_list=False):
            if soup_.strong.text.strip() != required_field_name:
                raise ValueError(
                    f'SearchResultItem could not be parsed correctly: Expected field "{required_field_name}"'
                    f', got field: "{soup_.strong.text.strip()}"')
            if as_list:
                return [x for x in [x.strip() for x in soup_.strong.next_sibling.split('\n')] if len(x) != 0]
            else:
                return soup_.strong.next_sibling.strip()

        top_level_fields = soup.div.findAll('p', recursive=False)
        second_level_fields = top_level_fields[4].findAll('p', recursive=False)

        name = top_level_fields[0].text.strip()
        address = top_level_fields[1].text.strip()
        vaccinations_offered = parse_strong_field(cls.VACCINATIONS_OFFERED_FIELD_NAME,
                                                  top_level_fields[2], as_list=True)
        age_groups_served = parse_strong_field(cls.AGE_GROUPS_SERVED_FIELD_NAME, top_level_fields[3])
        services_offered = parse_strong_field(cls.SERVICES_OFFERED_FIELD_NAME, second_level_fields[0], as_list=True)
        additional_information = parse_strong_field(cls.ADDITIONAL_INFORMATION_FIELD_NAME, second_level_fields[1])
        clinic_hours = parse_strong_field(cls.CLINIC_HOURS_FIELD_NAME, second_level_fields[2])
        appointments_available = int(parse_strong_field(cls.APPOINTMENTS_AVAILABLE_FIELD_NAME, second_level_fields[3]))
        special_instructions = parse_strong_field(cls.SPECIAL_INSTRUCTIONS_FIELD_NAME, top_level_fields[4].div)
        clinic_id_link = top_level_fields[4].a
        try:
            clinic_id = clinic_id_link['href'].split('clinic_id=')[1]
        except TypeError:
            try:
                clinic_id = soup.findChild('img')['src'].split('/')[-1].split('clinic')[1].split('.')[0]
            except (AttributeError, IndexError, TypeError):
                clinic_id = '0'
        return SearchResultItem(name, address, vaccinations_offered, age_groups_served, services_offered,
                                additional_information, clinic_hours, appointments_available, special_instructions,
                                clinic_id)


class Timeslot:
    def __init__(self, timestr, unixtime, available, appointments):
        self.timestr = timestr
        self.unixtime = unixtime
        self.available = available
        self.appointments = appointments

    @classmethod
    def from_html(cls, soup):
        time_choice_input = soup.td.input
        unixtime = time_choice_input['value']
        available = not time_choice_input.has_attr('disabled')
        timestr = soup.span.text.strip()
        try:
            appointments_paragraph = soup.findChildren('td')[1].p
            appointments_str = appointments_paragraph.text.split('appointments available')[0].strip()
            if appointments_str == 'No':
                appointments = 0
            else:
                appointments = int(appointments_str)
        except (AttributeError, IndexError, TypeError):
            appointments = 0
        return Timeslot(timestr, unixtime, available, appointments)


class ClinicWithFreeTimeslots(SearchResultItem):
    timeslots = []

    @classmethod
    def from_search_result_item(cls, search_result_item):
        return ClinicWithFreeTimeslots(name=search_result_item.name, address=search_result_item.address,
                                       vaccinations_offered=search_result_item.vaccinations_offered,
                                       age_groups_served=search_result_item.age_groups_served,
                                       services_offered=search_result_item.services_offered,
                                       additional_information=search_result_item.additional_information,
                                       clinic_hours=search_result_item.clinic_hours,
                                       appointments_available=search_result_item.appointments_available,
                                       special_instructions=search_result_item.special_instructions,
                                       clinic_id=search_result_item.clinic_id)


class DifferentialVaccinationAppointmentChecker:
    def __init__(self):
        self.clinic_id_map = {}

    @staticmethod
    def client_registration(clinic_id):
        FAILURE_REDIRECT_NO_APPOINTMENTS_AVAILABLE = \
            'https://www.vaccinateri.org/errors?' \
            'message=Clinic+does+not+have+any+appointment+slots+available.'
        FAILURE_REDIRECT_CLINIC_DOES_NOT_EXIST = \
            'https://www.vaccinateri.org/errors?' \
            'message=Deadline+to+register+for+this+clinic+has+been+reached.+Please+check+other+clinics.'
        FAILURE_REDIRECT_DEADLINE_REACHED = \
            'https://www.vaccinateri.org/errors?' \
            'message=Deadline+to+register+for+this+clinic+has+been+reached.+Please+check+other+clinics.'
        payload = {
            'clinic_id': clinic_id
        }
        timeslots = []
        r = requests.get(f'{SCHEME}{HOSTNAME}/client/registration', params=payload, allow_redirects=False)
        if r.status_code == 302:
            if r.headers['location'] == FAILURE_REDIRECT_NO_APPOINTMENTS_AVAILABLE:
                print(f'clinic_id {clinic_id} has no appointments available')
            elif r.headers['location'] == FAILURE_REDIRECT_CLINIC_DOES_NOT_EXIST:
                print(f'clinic_id {clinic_id} does not exist')
            elif r.headers['location'] == FAILURE_REDIRECT_DEADLINE_REACHED:
                print(f'clinic_id {clinic_id} registration deadline for date has been reached')
            else:
                print(f'Unknown redirect to {r.headers["location"]}')
            return []
        elif r.status_code != 200:
            print(f'Client registration for clinic_id {clinic_id} returned unexpected status code: {r.status_code}')
            print(f'{r.headers}')
            return []
        else:
            soup = BeautifulSoup(r.text, 'html.parser')
            appointments_table = soup.find(id='appointments-section').div.table
            appointment_trs = appointments_table.tbody.findAll('tr', recursive=False)
            for appointment_tr in appointment_trs:
                timeslot = Timeslot.from_html(appointment_tr)
                if timeslot.available:
                    timeslots.append(timeslot)
        return timeslots

    @staticmethod
    def clinic_search(location='', search_radius='All', venue_search_name_or_venue_name_i_cont='',
                      clinic_date_eq_year='',
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
                'class': ['md:flex', 'justify-between', '-mx-2', 'md:mx-0', 'px-2', 'md:px-4', 'pt-4', 'pb-4',
                          'border-b', 'border-gray-200']})
        search_result_items = []
        for item in search_results:
            search_result_items.append(SearchResultItem.from_html(item))
        return search_result_items

    def update(self, callback):
        search_result_items = DifferentialVaccinationAppointmentChecker.clinic_search()
        clinics_with_appointments_according_to_search = [item for item in search_result_items if
                                                         item.appointments_available > 0 and item.clinic_id != '0']
        total_appointments_according_to_search = reduce(lambda x, y: x + y.appointments_available,
                                                        clinics_with_appointments_according_to_search,
                                                        0)
        clinics_with_free_timeslots = []
        if total_appointments_according_to_search > 0:
            print(
                f'Search says there are a total of {total_appointments_according_to_search} appointments '
                f'available from {len(clinics_with_appointments_according_to_search)} different clinics')
        for clinic_with_appointments_available in clinics_with_appointments_according_to_search:
            timeslots = DifferentialVaccinationAppointmentChecker.client_registration(
                clinic_with_appointments_available.clinic_id)
            if len(timeslots) > 0:
                clinic_with_free_timeslots = ClinicWithFreeTimeslots.from_search_result_item(
                    clinic_with_appointments_available)
                clinic_with_free_timeslots.timeslots.extend(timeslots)
                clinics_with_free_timeslots.append(clinic_with_free_timeslots)

        old_clinic_id_map = deepcopy(self.clinic_id_map)
        self.clinic_id_map = {}
        for clinic_with_free_timeslots in clinics_with_free_timeslots:
            self.clinic_id_map[clinic_with_free_timeslots.clinic_id] = clinic_with_free_timeslots
            number_of_free_appointments = reduce(lambda x, y: x + y.appointments, clinic_with_free_timeslots.timeslots,
                                                 0)
            print(
                f'Clinic {clinic_with_free_timeslots.name} id: {clinic_with_free_timeslots.clinic_id} offers the '
                f'following free timeslots with a total of {number_of_free_appointments} appointments at '
                f'{SCHEME}{HOSTNAME}/client/registration?clinic_id={clinic_with_free_timeslots.clinic_id}:')
            for timeslot in clinic_with_free_timeslots.timeslots:
                print(f'    {timeslot.timestr} with {timeslot.appointments} free appointments')

        for clinic_id in self.clinic_id_map.keys():
            new_timeslots = []
            if clinic_id in old_clinic_id_map:
                for timeslot in self.clinic_id_map[clinic_id].timeslots:
                    is_new = True
                    for timeslot_old in old_clinic_id_map[clinic_id].timeslots:
                        if timeslot.unixtime == timeslot_old.unixtime:
                            is_new = False
                            break
                    if is_new:
                        new_timeslots.append(timeslot)
            else:
                new_timeslots.extend(self.clinic_id_map[clinic_id].timeslots)

            if len(new_timeslots) > 0:
                callback(self.clinic_id_map[clinic_id], new_timeslots)


def print_callback(clinic, timeslots):
    print(
        f'{len(timeslots)} new timeslots for {clinic.name} found: '
        f'{SCHEME}{HOSTNAME}/client/registration?clinic_id={clinic.clinic_id}')


def pushover_callback(clinic, timeslots):
    try:
        number_of_free_appointments = reduce(lambda x, y: x + y.appointments, timeslots, 0)
        requests.post("https://api.pushover.net/1/messages.json", data={
            "token": PUSHOVER_API_KEY,
            "user": PUSHOVER_USER_KEY,
            "message": f'{len(timeslots)} new timeslots with a total of {number_of_free_appointments} free appointments'
                       f' for {clinic.name} found: {SCHEME}{HOSTNAME}/client/registration?clinic_id={clinic.clinic_id}',
            "url": f'{SCHEME}{HOSTNAME}/client/registration?clinic_id={clinic.clinic_id}',
        })
    except Exception as e_:
        print(f'Notification could not be sent: {e_}')


if __name__ == '__main__':
    print(LOGO)
    if len(sys.argv) >= 3:
        PUSHOVER_USER_KEY = sys.argv[1]
        PUSHOVER_API_KEY = sys.argv[2]
        cb = pushover_callback
        print("[*] Using pushover notifications")
    else:
        print("Please supply pushover user and api keys as arguments to this script "
              "in order to allow pushover to notify you")
        print(f'Usage: {sys.argv[0]} PUSHOVER_USER_KEY PUSHOVER_API_KEY')
        cb = print_callback
        print("[*] Not using pushover notifications")
    print(f'[*] Updating every {INTERVAL} seconds')
    checker = DifferentialVaccinationAppointmentChecker()
    while True:
        try:
            checker.update(cb)
        except Exception as e:
            print(f'Update failed: {e}')
        time.sleep(INTERVAL)
