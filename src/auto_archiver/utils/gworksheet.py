from gspread import utils
from gspread_formatting import set_row_height
from gspread.exceptions import APIError
from time import sleep

class GWorksheet:
    """
    This class makes read/write operations to the a worksheet easier.
    It can read the headers from a custom row number, but the row references
    should always include the offset of the header. 
    eg: if header=4, row 5 will be the first with data. 
    """
    COLUMN_NAMES = {
        'uar': 'uar',
        'url': 'link',
        'status': 'media number + archive status',
        # 'folder': 'destination folder',
        'archive': 'additional information',
        'archived_filenames': 'archived file location(s)',
        'downloaded_filenames': 'original downloaded filename(s)',
        'date': 'archive date',
        'duration': 'duration (hh:mm:ss.mmmmmm)',
        'thumbnail': 'media thumbnail',
        'timestamp': 'upload timestamp utc',
        'timestamp_est': 'upload timestamp est',
        'title': 'upload title',
        'title_translated': 'upload title translated',
        'text': 'text of post',
        'text_translated': 'text of post translated',
        'screenshot': 'post screenshot link',
        'hash': 'hash',
        'codec_link': 'link for codec',
        'credit_string': 'credit'
        # 'pdq_hash': 'perceptual hashes',
        # 'wacz': 'wacz',
        # 'replaywebpage': 'replaywebpage'
    }

    COLS_TO_MERGE_IF_EXTRA_MEDIA = [
        'url',
        'archive',
        'date',
        'timestamp',
        'timestamp_est',
        'title',
        'title_translated',
        'text',
        'text_translated',
        'screenshot'
    ]

    def __init__(self, worksheet, columns=COLUMN_NAMES, header_row=1):
        self.wks = worksheet
        self.columns = columns
        while True:
            try:
                self.values = self.wks.get_values()
                break
            except APIError:
                sleep(60)
        if len(self.values) > 0:
            self.headers = [v.lower() for v in self.values[header_row - 1]]
        else:
            self.headers = []

    def _check_col_exists(self, col: str):
        if col not in self.columns:
            raise Exception(f'Column {col} is not in the configured column names: {self.columns.keys()}')

    def _col_index(self, col: str):
        self._check_col_exists(col)
        return self.headers.index(self.columns[col].lower())

    def col_exists(self, col: str):
        self._check_col_exists(col)
        return self.columns[col].lower() in self.headers

    def count_rows(self):
        return len(self.values)

    def get_row(self, row: int):
        # row is 1-based
        return self.values[row - 1]

    def get_values(self):
        return self.values
    
    def reload_sheet(self):
        while True:
            try:
                self.values = self.wks.get_values()
                break
            except APIError:
                sleep(60)

    def get_cell(self, row, col: str, fresh=False):
        """
        returns the cell value from (row, col), 
        where row can be an index (1-based) OR list of values
        as received from self.get_row(row)
        if fresh=True, the sheet is queried again for this cell
        """
        col_index = self._col_index(col)

        if fresh:
            # return self.wks.cell(row, col_index + 1).value
            self.reload_sheet()

        if type(row) == int:
            row = self.get_row(row)

        if col_index >= len(row):
            return ''
        return row[col_index]

    def get_cell_or_default(self, row, col: str, default: str = None, fresh=False, when_empty_use_default=True):
        """
        return self.get_cell or default value on error (eg: column is missing)
        """
        try:
            val = self.get_cell(row, col, fresh)
            if when_empty_use_default and val.strip() == "":
                return default
            return val
        except:
            return default

    def set_cell(self, row: int, col: str, val):
        # row is 1-based
        col_index = self._col_index(col) + 1
        while True:
            try:
                self.wks.update_cell(row, col_index, val)
                break
            except APIError:
                sleep(60)

    def batch_set_cell(self, cell_updates):
        """
        receives a list of [(row:int, col:str, val)] and batch updates it, the parameters are the same as in the self.set_cell() method
        """
        rows = set()
        for row, _, _ in cell_updates:
            while True:
                try:
                    set_row_height(self.wks, f"""{row}:{row}""", 200)
                    break
                except APIError:
                    sleep(60)

            rows.add(row)

        # if 106 in rows:
        #     rows = {106, 107, 108}
        # If all the rows are not equal, merge certain cells
        if len(rows) != 1:
            rows = sorted(rows)
            range_start = rows[0]
            range_end = rows[-1]
            for row in rows[:-1]:
                while True:
                    try:
                        self.wks.insert_row([], index=row)
                        break
                    except APIError:
                        sleep(60)

            for col in self.COLS_TO_MERGE_IF_EXTRA_MEDIA:
                while True:
                    try:
                        self.wks.merge_cells(range_start, self._col_index(col)+1, range_end, self._col_index(col)+1)
                        break
                    except APIError:
                        sleep(60)

        cell_updates = [
            {
                'range': self.to_a1(row, col),
                'values': [[str(val)[0:49999]]]
            }
            for row, col, val in cell_updates
        ]

        while True:
            try:
                self.wks.batch_update(cell_updates, value_input_option='USER_ENTERED')
                break
            except APIError:
                sleep(60)

        if len(rows) != 1:
            while True:
                try:
                    self.values = self.wks.get_values()
                    break
                except APIError:
                    sleep(60)

    def to_a1(self, row: int, col: str):
        # row is 1-based
        return utils.rowcol_to_a1(row, self._col_index(col) + 1)
