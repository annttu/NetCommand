
def expect_strings(answers):
    def expect_handler(row):
        for answer in answers.keys():
            if answer in row:
                return answers[answer]
        return None
    return expect_handler
